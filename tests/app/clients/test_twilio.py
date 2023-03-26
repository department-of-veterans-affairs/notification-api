import pytest
import requests_mock
from urllib.parse import parse_qsl

from app import twilio_sms_client
from app.clients.sms.twilio import get_twilio_responses
from twilio.base.exceptions import TwilioRestException

from tests.app.db import create_service_sms_sender


class MockSmsSenderObject():
    sms_sender = ""
    sms_sender_specifics = {}


def make_twilio_message_response_dict():
    return {
        "account_sid": "TWILIO_TEST_ACCOUNT_SID_XXX",
        "api_version": "2010-04-01",
        "body": "Hello! 👍",
        "date_created": "Thu, 30 Jul 2015 20:12:31 +0000",
        "date_sent": "Thu, 30 Jul 2015 20:12:33 +0000",
        "date_updated": "Thu, 30 Jul 2015 20:12:33 +0000",
        "direction": "outbound-api",
        "error_code": None,
        "error_message": None,
        "from": "+18194120710",
        "messaging_service_sid": "MGXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "num_media": "0",
        "num_segments": "1",
        "price": -0.00750,
        "price_unit": "USD",
        "sid": "MMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "status": "sent",
        "subresource_uris": {
            "media": "/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages"
                     "/SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/Media.json"
        },
        "to": "+14155552345",
        "uri": "/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages/SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.json",
    }


@pytest.fixture
def service_sms_sender():
    class ServiceSmsSender:
        def __init__(self):
            self.sms_sender = "Test Sender"
            self.sms_sender_specifics = {"messaging_service_sid": "test_messaging_service_sid"}

    return ServiceSmsSender()

@pytest.mark.parametrize("environment, expected_prefix", [
    ("staging", "staging-"),
    ("performance", "sandbox-"),
    ("production", ""),
    ("development", "dev-")
])
def test_send_sms_callback_url(mocker, service_sms_sender, environment, expected_prefix):
    to = "+1234567890"
    content = "Test message"
    reference = "test_reference"
    callback_notify_url_host = "https://api.va.gov"
    logger = mocker.Mock()

    # Mock the Twilio client
    twilio_client_mock = mocker.Mock(spec=Client)
    message_mock = mocker.Mock()
    message_mock.sid = "test_sid"
    twilio_client_mock.messages.create.return_value = message_mock

    mocker.patch("app.clients.sms.twilio.Client", return_value=twilio_client_mock)

    # Mock the dao functions
    mocker.patch("app.clients.sms.twilio.dao_get_service_sms_sender_by_service_id_and_number",
                 return_value=service_sms_sender)
    mocker.patch("app.clients.sms.twilio.dao_get_service_sms_sender_by_id",
                 return_value=service_sms_sender)

    twilio_sms_client.init_app(logger, callback_notify_url_host, environment)

    twilio_sms_client.send_sms(to, content, reference)

    twilio_client_mock.messages.create.assert_called_once_with(
        to=to,
        messaging_service_sid=service_sms_sender.sms_sender_specifics["messaging_service_sid"],
        body=content,
        status_callback=f"https://{expected_prefix}api.va.gov/vanotify/sms/deliverystatus"
    )

@pytest.mark.parametrize('status', ['queued', 'sending'])
def test_should_return_correct_details_for_sending(status):
    assert get_twilio_responses(status) == 'sending'


def test_should_return_correct_details_for_sent():
    assert get_twilio_responses('sent') == 'sent'


def test_should_return_correct_details_for_delivery():
    assert get_twilio_responses('delivered') == 'delivered'


def test_should_return_correct_details_for_bounce():
    assert get_twilio_responses('undelivered') == 'permanent-failure'


def test_should_return_correct_details_for_technical_failure():
    assert get_twilio_responses('failed') == 'technical-failure'


def test_should_be_raise_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        get_twilio_responses('unknown_status')
    assert 'unknown_status' in str(e.value)




def test_send_sms_calls_twilio_correctly(notify_api, mocker):
    to = '+61412345678'
    content = 'my message'
    reference = 'my reference'

    response_dict = make_twilio_message_response_dict()

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://api.twilio.com/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages.json',
                          json=response_dict, status_code=200)
        twilio_sms_client.send_sms(to, content, reference)

    assert request_mock.call_count == 1
    req = request_mock.request_history[0]
    assert req.url == 'https://api.twilio.com/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages.json'
    assert req.method == 'POST'

    d = dict(parse_qsl(req.text))
    assert d["To"] == "+61412345678"
    assert d["Body"] == "my message"


@pytest.mark.parametrize("sms_sender_id", ["test_sender_id", None], ids=["has sender id", "no sender id"])
def test_send_sms_call_with_sender_id_and_specifics(sample_service, notify_api, mocker, sms_sender_id):
    to = "+61412345678"
    content = "my message"
    reference = "my reference"
    sms_sender_specifics_info = {"messaging_service_sid": "test-service-sid-123"}

    create_service_sms_sender(
        service=sample_service,
        sms_sender="test_sender",
        is_default=False,
        sms_sender_specifics=sms_sender_specifics_info,
    )

    response_dict = make_twilio_message_response_dict()
    sms_sender_with_specifics = MockSmsSenderObject()
    sms_sender_with_specifics.sms_sender_specifics = sms_sender_specifics_info
    sms_sender_with_specifics.sms_sender = "+18194120710"

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://api.twilio.com/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages.json",
                          json=response_dict, status_code=200)

        if sms_sender_id is not None:
            mocker.patch("app.dao.service_sms_sender_dao.dao_get_service_sms_sender_by_id",
                         return_value=sms_sender_with_specifics)
        else:
            mocker.patch("app.dao.service_sms_sender_dao.dao_get_service_sms_sender_by_service_id_and_number",
                         return_value=sms_sender_with_specifics)

        twilio_sid = twilio_sms_client.send_sms(
            to,
            content,
            reference,
            service_id="test_service_id",
            sender="test_sender",
            sms_sender_id=sms_sender_id
        )

    assert response_dict['sid'] == twilio_sid

    assert request_mock.call_count == 1
    req = request_mock.request_history[0]
    assert req.url == "https://api.twilio.com/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages.json"
    assert req.method == "POST"

    d = dict(parse_qsl(req.text))

    assert d["To"] == "+61412345678"
    assert d["Body"] == "my message"
    assert d["MessagingServiceSid"] == "test-service-sid-123"


def test_send_sms_sends_from_hardcoded_number(notify_api, mocker):
    to = '+61412345678'
    content = 'my message'
    reference = 'my reference'

    response_dict = make_twilio_message_response_dict()

    sms_sender_mock = MockSmsSenderObject()
    sms_sender_mock.sms_sender = "+18194120710"

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://api.twilio.com/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages.json',
                          json=response_dict, status_code=200)
        mocker.patch('app.dao.service_sms_sender_dao.dao_get_service_sms_sender_by_service_id_and_number',
                     return_value=sms_sender_mock)
        twilio_sms_client.send_sms(to, content, reference)

    req = request_mock.request_history[0]

    d = dict(parse_qsl(req.text))
    assert d["From"] == "+18194120710"


def test_send_sms_raises_if_twilio_rejects(notify_api, mocker):
    to = '+61412345678'
    content = 'my message'
    reference = 'my reference'

    response_dict = {
        'code': 60082,
        'message': 'it did not work'
    }

    with pytest.raises(TwilioRestException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post('https://api.twilio.com/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages.json',
                          json=response_dict, status_code=400)
        twilio_sms_client.send_sms(to, content, reference)

    assert exc.value.status == 400
    assert exc.value.code == 60082
    assert exc.value.msg == "Unable to create record: it did not work"


def test_send_sms_raises_if_twilio_fails_to_return_json(notify_api, mocker):
    to = '+61412345678'
    content = 'my message'
    reference = 'my reference'

    response_dict = 'not JSON'

    with pytest.raises(ValueError), requests_mock.Mocker() as request_mock:
        request_mock.post('https://api.twilio.com/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages.json',
                          text=response_dict, status_code=200)
        twilio_sms_client.send_sms(to, content, reference)
