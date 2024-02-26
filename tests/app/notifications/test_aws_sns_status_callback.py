from app import create_uuid
import json
import pytest
from datetime import datetime
from freezegun import freeze_time
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from app.models import NOTIFICATION_FAILED, NOTIFICATION_SENT, Notification
from app.notifications.aws_sns_status_callback import SNS_STATUS_FAILURE, SNS_STATUS_SUCCESS, send_callback_metrics


@pytest.fixture
def mock_dao_get_notification_by_reference(mocker):
    return mocker.patch('app.notifications.aws_sns_status_callback.dao_get_notification_by_reference')


@pytest.fixture
def mock_update_notification_status(mocker):
    return mocker.patch('app.notifications.aws_sns_status_callback._update_notification_status')


@pytest.fixture
def mock_process_service_callback(mocker):
    return mocker.patch('app.notifications.aws_sns_status_callback.process_service_callback')


@pytest.fixture
def mock_send_callback_metrics(mocker):
    return mocker.patch('app.notifications.aws_sns_status_callback.send_callback_metrics')


@pytest.fixture
def mock_notification(mocker):
    notification = mocker.Mock(Notification)
    notification.id = create_uuid()
    notification.reference = create_uuid()
    notification.sent_at = datetime.utcnow()
    return notification


# https://docs.aws.amazon.com/sns/latest/dg/sms_stats_cloudwatch.html
def get_sns_delivery_status_payload(reference, status):
    return {
        'notification': {'messageId': reference, 'timestamp': '2016-06-28 00:40:34.558'},
        'delivery': {
            'phoneCarrier': 'My Phone Carrier',
            'mnc': 270,
            'destination': '+1XXX5550100',
            'priceInUSD': 0.00645,
            'smsType': 'Transactional',
            'mcc': 310,
            'providerResponse': 'Message has been accepted by phone carrier',
            'dwellTimeMs': 599,
            'dwellTimeMsUntilDeviceAck': 1344,
        },
        'status': status,
    }


def payload_with_missing_message_id():
    payload = get_sns_delivery_status_payload('some-reference', SNS_STATUS_SUCCESS)
    del payload['notification']['messageId']
    return payload


def payload_with_missing_status():
    payload = get_sns_delivery_status_payload('some-reference', SNS_STATUS_SUCCESS)
    del payload['status']
    return payload


def post(client, data):
    return client.post(
        path='/notifications/sms/sns', data=json.dumps(data), headers=[('Content-Type', 'application/json')]
    )


class TestSendcCllbackMetrics:
    @pytest.fixture
    def mocks_statsd(self, mocker):
        return mocker.patch('app.notifications.aws_sns_status_callback.statsd_client')

    @pytest.mark.parametrize('status', [NOTIFICATION_SENT, NOTIFICATION_FAILED])
    def test_should_increase_counter_for_status(self, client, mock_notification, mocks_statsd, status):
        mock_notification.status = status
        send_callback_metrics(mock_notification)
        mocks_statsd.incr.assert_called_with(f'callback.sns.{status}')

    @freeze_time('2020-11-03T22:45:00')
    @pytest.mark.parametrize('sent_at, should_call', [(None, False), (datetime(2020, 11, 3, 22, 30, 0), True)])
    def test_should_report_timing_only_when_notification_sent_at(
        self, client, mock_notification, mocks_statsd, sent_at, should_call
    ):
        mock_notification.sent_at = sent_at
        send_callback_metrics(mock_notification)
        if should_call:
            mocks_statsd.timing_with_dates.assert_called_with('callback.sns.elapsed-time', datetime.utcnow(), sent_at)
        else:
            mocks_statsd.timing_with_dates.assert_not_called
