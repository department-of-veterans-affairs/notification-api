import json
from uuid import uuid4

from botocore.stub import ANY

from flask import url_for
from flask_jwt_extended import create_access_token

import pytest

from app.celery.process_pinpoint_inbound_sms import CeleryEvent, process_pinpoint_inbound_sms
from app.dao.permissions_dao import permission_dao
from app.models import QUEUE_CHANNEL_TYPE, INBOUND_SMS_CALLBACK_TYPE, PLATFORM_ADMIN, Permission


# @pytest.fixture()
# def sqs_stub():
#     with Stubber(sqs_client._client) as stubber:
#         yield stubber
#         stubber.assert_no_pending_responses()


# @pytest.fixture()
# def integration_celery_config(notify_api):
#     with set_config_values(
#         notify_api,
#         {
#             'CELERY_SETTINGS': {
#                 'broker_url': 'sqs://',
#                 'task_always_eager': True,
#                 'imports': (
#                     'app.celery.tasks',
#                     'app.celery.scheduled_tasks',
#                     'app.celery.reporting_tasks',
#                     'app.celery.nightly_tasks',
#                     'app.celery.process_pinpoint_receipt_tasks',
#                     'app.celery.process_pinpoint_inbound_sms' 'app.celery.service_callback_tasks',
#                 ),
#             }
#         },
#     ):
#         notify_celery.init_app(notify_api)
#     yield
#     notify_celery.init_app(notify_api)


# @pytest.fixture
# def pinpoint_inbound_sms_toggle_enabled(mocker):
#     mock_feature_flag(mocker, FeatureFlag.PINPOINT_INBOUND_SMS_ENABLED, 'True')


class AnySms(object):
    def __init__(
        self, id=ANY, source_number=ANY, destination_number=ANY, message=ANY, date_received=ANY, sms_sender_id=ANY
    ):
        self.id = id
        self.source_number = source_number
        self.destination_number = destination_number
        self.message = message
        self.date_received = date_received
        self.sms_sender_id = sms_sender_id

    def __eq__(self, other):
        other_dict = json.loads(other)

        return (
            other_dict['source_number'] == self.source_number
            and other_dict['destination_number'] == self.destination_number
            and other_dict['message'] == self.message
            and other_dict['sms_sender_id'] == self.sms_sender_id
        )


@pytest.mark.skip(reason='Integration test fails when run in suite, passes when run alone')
def test_sqs_callback(integration_celery_config, sqs_stub, sample_service, client, pinpoint_inbound_sms_toggle_enabled):
    service = sample_service(
        service_name=f'sample service full permissions {uuid4()}',
        service_permissions=set(SERVICE_PERMISSION_TYPES),
        check_if_service_exists=True,
    )
    user = sample_service.users[0]
    permission_dao.set_user_service_permission(
        user, sample_service, [Permission(service_id=sample_service.id, user_id=user.id, permission=PLATFORM_ADMIN)]
    )
    user.platform_admin = True

    data = {
        'url': 'https://some.queue/inbound-sms-endpoint',
        'updated_by_id': str(sample_service.users[0].id),
        'callback_type': INBOUND_SMS_CALLBACK_TYPE,
        'callback_channel': QUEUE_CHANNEL_TYPE,
    }

    client.post(
        url_for('service_callback.create_service_callback', service_id=sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
    )

    message = {
        'messageBody': 'foo',
        'destinationNumber': '12345',  # set by sample_service_full_permissions
        'originationNumber': '123',
        'inboundMessageId': 'bar',
    }
    event: CeleryEvent = {'Message': json.dumps(message)}

    sqs_stub.add_response(
        'send_message',
        expected_params={
            'QueueUrl': data['url'],
            'MessageBody': AnySms(
                message=message['messageBody'],
                source_number=message['originationNumber'],
                destination_number=message['destinationNumber'],
                sms_sender_id=None,
            ),
            'MessageAttributes': ANY,
        },
        service_response={'MessageId': 'foo'},
    )

    process_pinpoint_inbound_sms(event)
