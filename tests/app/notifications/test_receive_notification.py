from datetime import datetime
from random import randint
from uuid import uuid4

import pytest
from freezegun import freeze_time

from app.constants import INBOUND_SMS_TYPE, SMS_TYPE
from app.models import Permission, Service
from app.notifications.receive_notifications import (
    NoSuitableServiceForInboundSms,
    create_inbound_sms_object,
    fetch_potential_service,
    format_mmg_datetime,
    format_mmg_message,
    strip_leading_forty_four,
    unescape_string,
)


@pytest.mark.parametrize(
    'permissions,expected_response',
    [
        ([SMS_TYPE, INBOUND_SMS_TYPE], True),
        ([INBOUND_SMS_TYPE], False),
        ([SMS_TYPE], False),
    ],
)
def test_check_permissions_for_inbound_sms(
    permissions,
    expected_response,
    sample_service,
):
    service = sample_service(service_permissions=permissions)
    assert service.has_permissions([INBOUND_SMS_TYPE, SMS_TYPE]) is expected_response


@pytest.mark.parametrize(
    'message, expected_output',
    [
        ('abc', 'abc'),
        ('', ''),
        ('lots+of+words', 'lots of words'),
        ('%F0%9F%93%A9+%F0%9F%93%A9+%F0%9F%93%A9', '📩 📩 📩'),
        ('x+%2B+y', 'x + y'),
    ],
)
def test_format_mmg_message(message, expected_output):
    assert format_mmg_message(message) == expected_output


@pytest.mark.parametrize(
    'raw, expected',
    [
        (
            '😬',
            '😬',
        ),
        (
            '1\\n2',
            '1\n2',
        ),
        (
            "\\'\"\\'",
            "'\"'",
        ),
        (
            """

        """,
            """

        """,
        ),
        (
            '\x79 \\x79 \\\\x79',  # we should never see the middle one
            'y y \\x79',
        ),
    ],
)
def test_unescape_string(raw, expected):
    assert unescape_string(raw) == expected


@pytest.mark.parametrize(
    'provider_date, expected_output',
    [
        ('2017-01-21+11%3A56%3A11', datetime(2017, 1, 21, 16, 56, 11)),
        ('2017-05-21+11%3A56%3A11', datetime(2017, 5, 21, 15, 56, 11)),
    ],
)
# This test assumes the local timezone is EST
def test_format_mmg_datetime(provider_date, expected_output):
    assert format_mmg_datetime(provider_date) == expected_output


# This test assumes the local timezone is EST
def test_create_inbound_mmg_sms_object(
    sample_service,
    sample_inbound_sms,
):
    service = sample_service()
    data = {
        'Message': 'hello+there+%F0%9F%93%A9',
        'Number': '+15551234566',
        'MSISDN': '447700900001',
        'DateReceived': '2017-01-02+03%3A04%3A05',
        'ID': 'bar',
    }
    inbound_sms = sample_inbound_sms(
        service=service,
        content=format_mmg_message(data['Message']),
        notify_number=data['Number'],
        user_number=data['MSISDN'],
        provider_reference=data['ID'],
        provider_date=format_mmg_datetime(data['DateReceived']),
        provider='mmg',
    )

    assert inbound_sms.service_id == service.id
    assert inbound_sms.notify_number == '+15551234566'
    assert inbound_sms.user_number == '447700900001'
    assert inbound_sms.provider_date == datetime(2017, 1, 2, 8, 4, 5)
    assert inbound_sms.provider_reference == 'bar'
    assert inbound_sms._content != 'hello there 📩'
    assert inbound_sms.content == 'hello there 📩'
    assert inbound_sms.provider == 'mmg'


@pytest.mark.parametrize(
    'number, expected',
    [
        ('447123123123', '07123123123'),
        ('447123123144', '07123123144'),
        ('07123123123', '07123123123'),
        ('447444444444', '07444444444'),
    ],
)
def test_strip_leading_country_code(number, expected):
    assert strip_leading_forty_four(number) == expected


@freeze_time('2017-01-01T16:00:00')
def test_create_inbound_sms_object(
    sample_service,
):
    service = sample_service()
    ref = str(uuid4())
    number = f'+1{randint(1000000000, 9999999999)}'
    inbound_sms = create_inbound_sms_object(
        service=service,
        content='hello there 📩',
        notify_number=number,
        from_number='+61412345678',
        provider_ref=ref,
        date_received=datetime.utcnow(),
        provider_name='twilio',
    )

    assert inbound_sms.service_id == service.id
    assert inbound_sms.notify_number == number
    assert inbound_sms.user_number == '+61412345678'
    assert inbound_sms.provider_date == datetime(2017, 1, 1, 16, 00, 00)
    assert inbound_sms.provider_reference == ref
    assert inbound_sms._content != 'hello there 📩'
    assert inbound_sms.content == 'hello there 📩'
    assert inbound_sms.provider == 'twilio'

    # Teardown


def test_create_inbound_sms_object_works_with_alphanumeric_sender(
    sample_inbound_sms,
    sample_service,
):
    service = sample_service()
    data = {
        'Message': 'hello',
        'Number': '+15551234567',
        'MSISDN': 'ALPHANUM3R1C',
        'DateReceived': '2017-01-02+03%3A04%3A05',
        'ID': 'bar',
    }

    inbound_sms = sample_inbound_sms(
        service=service,
        content=format_mmg_message(data['Message']),
        notify_number='+15551234567',
        user_number='ALPHANUM3R1C',
        provider_reference='foo',
        provider_date=None,
        provider='mmg',
    )

    assert inbound_sms.user_number == 'ALPHANUM3R1C'


class TestFetchPotentialService:
    def test_should_raise_if_no_matching_service(self, notify_api, mocker):
        mocker.patch('app.notifications.receive_notifications.dao_fetch_service_by_inbound_number', return_value=None)

        with pytest.raises(NoSuitableServiceForInboundSms):
            fetch_potential_service('some-inbound-number', 'some-provider-name')

    def test_should_raise_if_service_doesnt_have_permission(self, notify_api, mocker):
        # make mocked service execute original code
        # just mocking service won't let us execute .has_permissions
        # method properly
        mock_service_instance = Service(permissions=[])
        mocker.patch(
            'app.notifications.receive_notifications.dao_fetch_service_by_inbound_number',
            return_value=mock_service_instance,
        )

        with pytest.raises(NoSuitableServiceForInboundSms):
            fetch_potential_service('some-inbound-number', 'some-provider-name')

    def test_should_return_service_with_permission(self, notify_api, mocker):
        service = mocker.Mock(
            Service,
            permissions=[
                mocker.Mock(Permission, permission=INBOUND_SMS_TYPE),
                mocker.Mock(Permission, permission=SMS_TYPE),
            ],
        )
        mocker.patch(
            'app.notifications.receive_notifications.dao_fetch_service_by_inbound_number', return_value=service
        )

        assert fetch_potential_service('some-inbound-number', 'some-provider-name') == service
