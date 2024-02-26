import app.celery.tasks
import json
import pytest
import pytz
import uuid
from app.dao.templates_dao import dao_update_template
from app.models import JOB_STATUS_TYPES, JOB_STATUS_PENDING
from datetime import datetime, timedelta, date
from freezegun import freeze_time
from tests import create_admin_authorization_header
from tests.app.db import create_ft_notification_status, create_job, create_notification
from tests.conftest import set_config


@pytest.mark.xfail(reason='Failing after Flask upgrade.  Not fixed because not used.', run=False)
def test_create_unscheduled_job(client, sample_template, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch(
        'app.job.rest.get_job_metadata_from_s3',
        return_value={
            'template_id': str(sample_template.id),
            'original_file_name': 'thisisatest.csv',
            'notification_count': '1',
            'valid': 'True',
        },
    )
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_admin_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_called_once_with(
        ([str(fake_uuid)]), {'sender_id': None}, queue='job-tasks'
    )

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['data']['id'] == fake_uuid
    assert resp_json['data']['statistics'] == []
    assert resp_json['data']['job_status'] == 'pending'
    assert not resp_json['data']['scheduled_for']
    assert resp_json['data']['job_status'] == 'pending'
    assert resp_json['data']['template'] == str(sample_template.id)
    assert resp_json['data']['original_file_name'] == 'thisisatest.csv'
    assert resp_json['data']['notification_count'] == 1


@pytest.mark.xfail(reason='Failing after Flask upgrade.  Not fixed because not used.', run=False)
def test_create_unscheduled_job_with_sender_id_in_metadata(client, sample_template, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch(
        'app.job.rest.get_job_metadata_from_s3',
        return_value={
            'template_id': str(sample_template.id),
            'original_file_name': 'thisisatest.csv',
            'notification_count': '1',
            'valid': 'True',
            'sender_id': fake_uuid,
        },
    )
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_admin_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_called_once_with(
        ([str(fake_uuid)]), {'sender_id': fake_uuid}, queue='job-tasks'
    )


@pytest.mark.xfail(reason='Failing after Flask upgrade.  Not fixed because not used.', run=False)
@freeze_time('2016-01-01 12:00:00.000000')
def test_create_scheduled_job(client, sample_template, mocker, fake_uuid):
    scheduled_date = (datetime.utcnow() + timedelta(hours=95, minutes=59)).isoformat()
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch(
        'app.job.rest.get_job_metadata_from_s3',
        return_value={
            'template_id': str(sample_template.id),
            'original_file_name': 'thisisatest.csv',
            'notification_count': '1',
            'valid': 'True',
        },
    )
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
        'scheduled_for': scheduled_date,
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_admin_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_not_called()

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['data']['id'] == fake_uuid
    assert resp_json['data']['scheduled_for'] == datetime(2016, 1, 5, 11, 59, 0, tzinfo=pytz.UTC).isoformat()
    assert resp_json['data']['job_status'] == 'scheduled'
    assert resp_json['data']['template'] == str(sample_template.id)
    assert resp_json['data']['original_file_name'] == 'thisisatest.csv'
    assert resp_json['data']['notification_count'] == 1
