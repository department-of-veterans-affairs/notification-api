import pytest
from datetime import datetime

import boto3
from flask import current_app
from freezegun import freeze_time
from moto import mock_s3

from app.letters.utils import (
    copy_redaction_failed_pdf,
    get_bucket_name_and_prefix_for_notification,
    get_letter_pdf_filename,
    letter_print_day,
    upload_letter_pdf,
    ScanErrorType,
    move_failed_pdf,
    get_folder_name,
)
from app.models import (
    KEY_TYPE_TEST,
    PRECOMPILED_TEMPLATE_NAME,
    SERVICE_PERMISSION_TYPES,
)
from tests.app.db import LETTER_TYPE

FROZEN_DATE_TIME = '2018-03-14 17:00:00'


@pytest.fixture(name='sample_precompiled_letter_notification')
def _sample_precompiled_letter_notification(sample_letter_notification):
    sample_letter_notification.template.hidden = True
    sample_letter_notification.template.name = PRECOMPILED_TEMPLATE_NAME
    sample_letter_notification.reference = 'foo'
    with freeze_time(FROZEN_DATE_TIME):
        sample_letter_notification.created_at = datetime.utcnow()
        sample_letter_notification.updated_at = datetime.utcnow()
    return sample_letter_notification


@pytest.fixture(name='sample_precompiled_letter_notification_using_test_key')
def _sample_precompiled_letter_notification_using_test_key(sample_precompiled_letter_notification):
    sample_precompiled_letter_notification.key_type = KEY_TYPE_TEST
    return sample_precompiled_letter_notification


def test_get_bucket_name_and_prefix_for_notification_get_from_sent_at_date(
    sample_api_key,
    sample_template,
    sample_notification,
):
    template = sample_template()
    api_key = sample_api_key(service=template.service)
    notification = sample_notification(
        template=template,
        api_key=api_key,
        created_at=datetime(2019, 8, 1, 17, 35),
        sent_at=datetime(2019, 8, 2, 17, 45),
    )

    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(notification)

    assert bucket == current_app.config['LETTERS_PDF_BUCKET_NAME']
    assert bucket_prefix == f'2019-08-02/NOTIFY.{notification.reference}'.upper()


def test_get_bucket_name_and_prefix_for_notification_from_created_at_date(
    sample_api_key,
    sample_template,
    sample_notification,
):
    template = sample_template()
    api_key = sample_api_key(service=template.service)
    notification = sample_notification(
        template=template,
        api_key=api_key,
        created_at=datetime(2019, 8, 1, 12, 00),
        updated_at=datetime(2019, 8, 2, 12, 00),
        sent_at=datetime(2019, 8, 3, 12, 00),
    )

    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(notification)

    assert bucket == current_app.config['LETTERS_PDF_BUCKET_NAME']
    assert bucket_prefix == f'2019-08-03/NOTIFY.{notification.reference}'.upper()


def test_get_bucket_name_and_prefix_for_notification_invalid_notification():
    with pytest.raises(AttributeError):
        get_bucket_name_and_prefix_for_notification(None)


@pytest.mark.parametrize(
    'crown_flag,expected_crown_text',
    [
        (True, 'C'),
        (False, 'N'),
    ],
)
@freeze_time('2017-12-04 17:29:00')
def test_get_letter_pdf_filename_returns_correct_filename(notify_api, mocker, crown_flag, expected_crown_text):
    filename = get_letter_pdf_filename(reference='foo', crown=crown_flag)

    assert filename == '2017-12-04/NOTIFY.FOO.D.2.C.{}.20171204172900.PDF'.format(expected_crown_text)


@pytest.mark.parametrize(
    'postage,expected_postage',
    [
        ('second', 2),
        ('first', 1),
    ],
)
@freeze_time('2017-12-04 17:29:00')
def test_get_letter_pdf_filename_returns_correct_postage_for_filename(notify_api, postage, expected_postage):
    filename = get_letter_pdf_filename(reference='foo', crown=True, postage=postage)

    assert filename == '2017-12-04/NOTIFY.FOO.D.{}.C.C.20171204172900.PDF'.format(expected_postage)


@freeze_time('2017-12-04 17:29:00')
def test_get_letter_pdf_filename_returns_correct_filename_for_test_letters(notify_api, mocker):
    filename = get_letter_pdf_filename(reference='foo', crown='C', is_scan_letter=True)

    assert filename == 'NOTIFY.FOO.D.2.C.C.20171204172900.PDF'


@pytest.mark.parametrize('postage,expected_postage', [('second', 2), ('first', 1)])
def test_upload_letter_pdf_uses_postage_from_notification(
    sample_api_key,
    sample_notification,
    sample_service,
    sample_template,
    mocker,
    postage,
    expected_postage,
):
    service = sample_service(service_permissions=set(SERVICE_PERMISSION_TYPES), check_if_service_exists=True)
    api_key = sample_api_key(service=service)
    template = sample_template(service=service, template_type=LETTER_TYPE, postage='second')
    letter_notification = sample_notification(template=template, api_key=api_key, postage=postage)
    mock_s3 = mocker.patch('app.letters.utils.s3upload')

    filename = upload_letter_pdf(letter_notification, b'\x00\x01', precompiled=False)

    mock_s3.assert_called_once_with(
        bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
        file_location=filename,
        filedata=b'\x00\x01',
        region=current_app.config['AWS_REGION'],
    )


@mock_s3
@freeze_time(FROZEN_DATE_TIME)
def test_move_failed_pdf_error(notify_api, aws_credentials):
    filename = 'test.pdf'
    bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='us-east-1')
    bucket = conn.create_bucket(Bucket=bucket_name)

    s3 = boto3.client('s3', region_name='us-east-1')
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b'pdf_content')

    move_failed_pdf(filename, ScanErrorType.ERROR)

    assert 'ERROR/' + filename in [o.key for o in bucket.objects.all()]
    assert filename not in [o.key for o in bucket.objects.all()]


@mock_s3
@freeze_time(FROZEN_DATE_TIME)
def test_move_failed_pdf_scan_failed(notify_api, aws_credentials):
    filename = 'test.pdf'
    bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='us-east-1')
    bucket = conn.create_bucket(Bucket=bucket_name)

    s3 = boto3.client('s3', region_name='us-east-1')
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b'pdf_content')

    move_failed_pdf(filename, ScanErrorType.FAILURE)

    assert 'FAILURE/' + filename in [o.key for o in bucket.objects.all()]
    assert filename not in [o.key for o in bucket.objects.all()]


@mock_s3
@freeze_time(FROZEN_DATE_TIME)
def test_copy_redaction_failed_pdf(notify_api, aws_credentials):
    filename = 'test.pdf'
    bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='us-east-1')
    bucket = conn.create_bucket(Bucket=bucket_name)

    s3 = boto3.client('s3', region_name='us-east-1')
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b'pdf_content')

    copy_redaction_failed_pdf(filename)

    assert 'REDACTION_FAILURE/' + filename in [o.key for o in bucket.objects.all()]
    assert filename in [o.key for o in bucket.objects.all()]


def test_get_folder_name_returns_empty_string_for_test_letter():
    assert '' == get_folder_name(datetime.utcnow(), is_test_or_scan_letter=True)


@freeze_time('2017-07-07 16:30:00')
def test_letter_print_day_returns_today_if_letter_was_printed_today():
    created_at = datetime(2017, 7, 7, 12, 0)
    assert letter_print_day(created_at) == 'today'
