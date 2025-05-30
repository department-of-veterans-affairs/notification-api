import json
from uuid import uuid4

import pytest
from flask import url_for
from flask_jwt_extended import create_access_token
from freezegun import freeze_time
from sqlalchemy import select

from app.constants import (
    COMPLAINT_CALLBACK_TYPE,
    DELIVERY_STATUS_CALLBACK_TYPE,
    INBOUND_SMS_CALLBACK_TYPE,
    MANAGE_SETTINGS,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_STATUS_TYPES_COMPLETED,
    QUEUE_CHANNEL_TYPE,
    WEBHOOK_CHANNEL_TYPE,
)
from app.dao.services_dao import dao_add_user_to_service
from app.models import Permission, ServiceCallback
from app.schemas import service_callback_api_schema
from tests.app.conftest import json_compare


class TestFetchServiceCallback:
    def test_fetch_service_callback_works_with_user_permisisons(
        self,
        client,
        sample_service_callback,
        sample_service,
        sample_user,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service=service)
        original_user = service.users[0]
        user = sample_user(email=f'foo{uuid4()}@bar.com')
        dao_add_user_to_service(
            service, user, permissions=[Permission(service=service, user=user, permission=MANAGE_SETTINGS)]
        )
        token = create_access_token(user)

        response = client.get(
            url_for(
                'service_callback.fetch_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            headers=[('Authorization', f'Bearer {token}')],
        )
        assert response.status_code == 200
        assert response.json['data'] == {
            'id': str(service_callback_api.id),
            'service_id': str(service_callback_api.service_id),
            'url': service_callback_api.url,
            'updated_by_id': str(original_user.id),
            'created_at': str(service_callback_api.created_at),
            'updated_at': service_callback_api.updated_at,
            'notification_statuses': service_callback_api.notification_statuses,
            'callback_type': service_callback_api.callback_type,
            'callback_channel': service_callback_api.callback_channel,
            'include_provider_payload': service_callback_api.include_provider_payload,
        }

    def test_fetch_service_callback_works_with_platform_admin(
        self,
        client,
        sample_service_callback,
        sample_service,
        sample_user,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service=service)
        user = sample_user(email=f'foo{uuid4()}@bar.com', platform_admin=True)
        token = create_access_token(user)

        response = client.get(
            url_for(
                'service_callback.fetch_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            headers=[('Authorization', f'Bearer {token}')],
        )
        assert response.status_code == 200
        assert response.json['data'] == service_callback_api_schema.dump(service_callback_api)

    def test_should_return_404_if_trying_to_fetch_callback_from_different_service(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        another_service = sample_service(service_name=f'callback service {uuid4()}')
        service_callback_api = sample_service_callback(another_service)

        response = client.get(
            url_for(
                'service_callback.fetch_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            headers=[('Authorization', f'Bearer {create_access_token(service.users[0])}')],
        )
        assert response.status_code == 404


class TestFetchServiceCallbacks:
    def test_fetch_service_callbacks_works_with_user_permisisons(
        self,
        client,
        sample_service_callback,
        sample_service,
        sample_user,
    ):
        service = sample_service()
        service_callbacks = [
            sample_service_callback(service=service),
            sample_service_callback(service=service, callback_type=INBOUND_SMS_CALLBACK_TYPE),
        ]
        user = sample_user(email=f'foo{uuid4()}@bar.com')
        dao_add_user_to_service(
            service, user, permissions=[Permission(service=service, user=user, permission=MANAGE_SETTINGS)]
        )
        token = create_access_token(user)

        response = client.get(
            url_for('service_callback.fetch_service_callbacks', service_id=service.id),
            headers=[('Authorization', f'Bearer {token}')],
        )
        assert response.status_code == 200
        assert json_compare(
            response.json['data'],
            [service_callback_api_schema.dump(s) for s in service_callbacks],
        )

    @freeze_time('1990-12-04 16:00:00.000000')
    def test_fetch_service_callbacks_works_with_platform_admin(
        self,
        client,
        sample_service,
        sample_user,
        sample_service_callback,
    ):
        service = sample_service()
        service_callbacks = [
            sample_service_callback(service=service),
            sample_service_callback(service=service, callback_type=INBOUND_SMS_CALLBACK_TYPE),
        ]

        user = sample_user(email=f'foo{uuid4()}@bar.com', platform_admin=True)
        token = create_access_token(user)

        response = client.get(
            url_for('service_callback.fetch_service_callbacks', service_id=service.id),
            headers=[('Authorization', f'Bearer {token}')],
        )
        assert response.status_code == 200
        assert json_compare(
            response.json['data'],
            [service_callback_api_schema.dump(s) for s in service_callbacks],
        )


class TestCreateServiceCallback:
    def test_create_service_callback_raises_404_when_service_does_not_exist_for_platform_admin(
        self, client, sample_user
    ):
        user = sample_user(email=f'foo{uuid4()}@bar.com', platform_admin=True)
        token = create_access_token(user)

        data = {
            'url': 'https://some.service/callback-sms',
            'bearer_token': 'some-unique-string',
            'notification_statuses': ['sent'],
            'callback_channel': WEBHOOK_CHANNEL_TYPE,
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
        }
        response = client.post(
            url_for('service_callback.create_service_callback', service_id=str(uuid4())),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {token}')],
        )
        assert response.status_code == 404
        assert response.json['message'] == 'No result found'

    @pytest.mark.parametrize(
        'callback_type, has_notification_statuses',
        [(DELIVERY_STATUS_CALLBACK_TYPE, True), (INBOUND_SMS_CALLBACK_TYPE, False), (COMPLAINT_CALLBACK_TYPE, False)],
    )
    def test_create_service_callback(
        self, client, sample_service, callback_type, has_notification_statuses, notify_db_session
    ):
        service = sample_service()
        user = service.users[0]
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'bearer_token': 'some-unique-string',
            'callback_type': callback_type,
            'callback_channel': WEBHOOK_CHANNEL_TYPE,
        }
        if has_notification_statuses:
            data['notification_statuses'] = ['failed']

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 201
        resp_json = response.json['data']
        assert resp_json['id']
        assert resp_json['service_id'] == str(service.id)
        assert resp_json['url'] == 'https://some.service/delivery-receipt-endpoint'
        assert resp_json['updated_by_id'] == str(user.id)
        assert resp_json['created_at']
        assert not resp_json['updated_at']
        assert resp_json.get('bearer_token') is None
        created_service_callback_api = notify_db_session.session.get(ServiceCallback, resp_json['id'])
        assert created_service_callback_api.callback_type == callback_type
        if has_notification_statuses:
            assert created_service_callback_api.notification_statuses == ['failed']

    def test_create_service_callback_creates_delivery_status_with_default_statuses_if_no_statuses_passed(
        self, client, sample_service, notify_db_session
    ):
        service = sample_service()
        user = service.users[0]
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'bearer_token': 'some-unique-string',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'callback_channel': WEBHOOK_CHANNEL_TYPE,
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        resp_json = response.json['data']
        created_service_callback_api = notify_db_session.session.get(ServiceCallback, resp_json['id'])

        # Database returns it as a list, but it is declared in code as a tuple
        assert created_service_callback_api.notification_statuses == list(NOTIFICATION_STATUS_TYPES_COMPLETED)

    @pytest.mark.parametrize('callback_type', [INBOUND_SMS_CALLBACK_TYPE, COMPLAINT_CALLBACK_TYPE])
    def test_create_service_callback_returns_400_if_statuses_passed_with_incompatible_callback_type(
        self, client, sample_service, callback_type
    ):
        service = sample_service()
        user = service.users[0]
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'bearer_token': 'some-unique-string',
            'callback_type': callback_type,
            'notification_statuses': NOTIFICATION_STATUS_TYPES_COMPLETED,
            'callback_channel': WEBHOOK_CHANNEL_TYPE,
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 400
        resp_json = response.json
        assert resp_json['result'] == 'error'
        error_message = resp_json['message']['_schema'][0]
        assert error_message == f'Callback type {callback_type} should not have notification statuses'

    def test_create_service_callback_returns_400_if_no_bearer_token_for_webhook(self, client, sample_service):
        service = sample_service()
        user = service.users[0]
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'notification_statuses': NOTIFICATION_STATUS_TYPES_COMPLETED,
            'callback_channel': WEBHOOK_CHANNEL_TYPE,
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 400
        resp_json = response.json
        assert resp_json['result'] == 'error'
        assert resp_json['message']['_schema'][0] == f'Callback channel {WEBHOOK_CHANNEL_TYPE} should have bearer_token'

    def test_create_service_callback_returns_400_for_invalid_callback_channel(self, client, sample_service):
        service = sample_service()
        user = service.users[0]
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'bearer_token': 'some-unique-string',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'notification_statuses': NOTIFICATION_STATUS_TYPES_COMPLETED,
            'callback_channel': 'invalid_channel_type',
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 400
        resp_json = response.json
        assert resp_json['errors'][0]['error'] == 'ValidationError'
        assert (
            resp_json['errors'][0]['message'] == f'callback_channel {data["callback_channel"]} is not one of '
            f'[webhook, queue]'
        )

    def test_users_cannot_create_service_callbacks_with_queue_channel(self, client, sample_service):
        service = sample_service()
        user = service.users[0]
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'notification_statusmes': NOTIFICATION_STATUS_TYPES_COMPLETED,
            'callback_channel': QUEUE_CHANNEL_TYPE,
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 403
        error_message = response.json['message']
        assert error_message == 'User does not have permissions to create callbacks of channel type queue'

    def test_platform_admin_can_create_queue_service_callback(self, client, sample_service, sample_user):
        user = sample_user(email=f'foo{uuid4()}@bar.com', platform_admin=True)
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'notification_statuses': NOTIFICATION_STATUS_TYPES_COMPLETED,
            'callback_channel': QUEUE_CHANNEL_TYPE,
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=sample_service().id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 201

    def test_create_service_callback_raises_400_when_notification_status_validation_failed(self, client, sample_user):
        non_existent_status = 'nonexistent_failed'
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'bearer_token': 'some-unique-string',
            'notification_statuses': [non_existent_status],
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=str(uuid4())),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(sample_user(platform_admin=True))}'),
            ],
        )
        assert response.status_code == 400

    @pytest.mark.parametrize(
        'add_url, url, expected_response',
        [
            (False, None, 'url is a required property'),
            (True, None, 'url is not a valid https url'),
            (True, 'broken.url', 'url is not a valid https url'),
        ],
    )
    def test_create_service_callback_raises_400_when_url_validation_failed(
        self, sample_service, client, add_url, url, expected_response
    ):
        service = sample_service()
        user = service.users[0]
        data = {
            'bearer_token': 'some-unique-string',
            'notification_statuses': ['failed'],
        }
        if add_url:
            data['url'] = url

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )
        assert response.status_code == 400
        resp_json = response.json
        assert resp_json['errors'][0]['error'] == 'ValidationError'
        assert resp_json['errors'][0]['message'] == expected_response

    @pytest.mark.parametrize(
        'add_bearer_token, bearer_token, expected_response',
        [
            (True, None, 'bearer_token None is not of type string'),
            (True, 'too-short', 'bearer_token too-short is too short'),
        ],
    )
    def test_create_service_callback_raises_400_when_bearer_token_validation_failed(
        self, client, sample_service, add_bearer_token, bearer_token, expected_response
    ):
        service = sample_service()
        user = service.users[0]
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'notification_statuses': ['failed'],
        }
        if add_bearer_token:
            data['bearer_token'] = bearer_token

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 400
        resp_json = response.json
        assert resp_json['errors'][0]['error'] == 'ValidationError'
        assert resp_json['errors'][0]['message'] == expected_response

    def test_create_service_callback_returns_409_when_webhook_callback_already_exists(self, client, sample_service):
        service = sample_service()
        user = service.users[0]

        # Create first webhook callback
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'bearer_token': 'some-unique-string',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'notification_statuses': ['failed'],
            'callback_channel': WEBHOOK_CHANNEL_TYPE,
        }

        # The sample_service() fixture cleanup will remove the webhook callback
        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 201

        # Try to create second webhook callback
        new_data = data.copy()
        new_data['url'] = 'https://another.service/delivery-receipt-endpoint'
        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(new_data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 409
        assert response.json['message'] == 'A webhook callback already exists for this service'
        # The sample_service() fixture cleanup will remove any created callbacks

    def test_create_service_callback_returns_409_when_queue_callback_already_exists(
        self, client, sample_service, sample_user
    ):
        service = sample_service()
        user = sample_user(email=f'foo{uuid4()}@bar.com', platform_admin=True)

        # Create first queue callback
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'notification_statuses': ['failed'],
            'callback_channel': QUEUE_CHANNEL_TYPE,
        }

        # The sample_service() fixture cleanup will remove the queue callback
        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 201

        # Try to create second queue callback
        data['url'] = 'https://another.service/delivery-receipt-endpoint'
        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 409
        assert response.json['message'] == 'A queue callback already exists for this service'
        # The sample_service() fixture cleanup will remove any created callbacks

    def test_create_service_callback_returns_409_when_callback_type_already_exists(
        self, client, sample_service, sample_user
    ):
        service = sample_service()
        user = sample_user(email=f'foo{uuid4()}@bar.com', platform_admin=True)

        # Create first delivery status callback
        data = {
            'url': 'https://some.service/delivery-receipt-endpoint',
            'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
            'notification_statuses': ['failed'],
            'callback_channel': QUEUE_CHANNEL_TYPE,
        }

        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 201

        # Try to create second delivery status callback with different channel
        data['url'] = 'https://another.service/delivery-receipt-endpoint'
        data['callback_channel'] = WEBHOOK_CHANNEL_TYPE
        response = client.post(
            url_for('service_callback.create_service_callback', service_id=service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.status_code == 409
        assert response.json['message'] == 'A delivery_status callback already exists for this service'
        # The sample_service() fixture cleanup will remove any created callbacks


class TestUpdateServiceCallback:
    def test_update_service_callback_updates_url(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service=service, url='https://originalurl.com')

        data = {'url': 'https://anotherurl.com'}

        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )

        assert response.status_code == 200
        assert response.json['data']['url'] == 'https://anotherurl.com'
        assert service_callback_api.url == 'https://anotherurl.com'

    def test_update_service_callback_updates_bearer_token(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service=service, bearer_token='some_super_secret')
        data = {
            'bearer_token': 'different_token',
        }

        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )
        assert response.status_code == 200
        assert service_callback_api.bearer_token == 'different_token'

    def test_update_service_callback_updates_notification_statuses(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service=service, notification_statuses=['cancelled'])
        data = {
            'notification_statuses': ['delivered'],
        }

        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )
        assert response.status_code == 200
        resp_json = response.json
        assert resp_json['data']['notification_statuses'] == ['delivered']
        assert resp_json.get('bearer_token') is None

    def test_update_service_callback_updates_include_provider_payload(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service=service, include_provider_payload=False)
        data = {
            'include_provider_payload': True,
        }

        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )

        assert response.status_code == 200
        assert service_callback_api.include_provider_payload is True

    @pytest.mark.idparametrize(
        'request_data',
        {
            'invalid_property': (
                {
                    'invalid_parameter': ['failed'],
                }
            ),
            'empty_request': ({}),
        },
    )
    def test_update_service_callback_raises_400_when_wrong_request(
        self,
        client,
        sample_service_callback,
        sample_service,
        request_data,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(
            service=service, notification_statuses=[NOTIFICATION_PERMANENT_FAILURE]
        )

        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(request_data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )

        assert response.status_code == 400
        resp_json = response.json
        assert len(resp_json['errors']) > 0
        for error in resp_json['errors']:
            assert error['message'] is not None

    def test_update_service_callback_raises_400_when_invalid_status(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(
            service=service, notification_statuses=[NOTIFICATION_PERMANENT_FAILURE]
        )

        data = {
            'notification_statuses': ['nonexistent-status'],
        }

        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )
        assert response.status_code == 400
        resp_json = response.json
        assert resp_json['errors'][0]['error'] == 'ValidationError'
        assert 'notification_statuses nonexistent-status is not one of' in resp_json['errors'][0]['message']

    def test_update_service_callback_modifies_updated_at(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        with freeze_time('2021-05-13 12:00:00.000000'):
            service = sample_service()
            service_callback_api = sample_service_callback(
                service=service,
                bearer_token='some_super_secret',
            )
            data = {'url': 'https://some.service'}

            response = client.post(
                url_for(
                    'service_callback.update_service_callback',
                    service_id=service.id,
                    callback_id=service_callback_api.id,
                ),
                data=json.dumps(data),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
                ],
            )

        assert response.json['data']['updated_at'] == '2021-05-13T12:00:00'

    def test_update_service_callback_modifies_updated_by(
        self,
        client,
        sample_service_callback,
        sample_service,
        sample_user,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service=service)
        user = sample_user(email=f'foo{uuid4()}@bar.com')
        dao_add_user_to_service(
            service, user, permissions=[Permission(service=service, user=user, permission=MANAGE_SETTINGS)]
        )

        data = {'url': 'https://some.service'}

        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )

        assert response.json['data']['updated_by_id'] == str(user.id)

    def test_update_service_callback_should_return_403_if_not_authorized(
        self,
        client,
        sample_service_callback,
        sample_service,
        sample_user,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service)
        user = sample_user(email=f'foo{uuid4()}@bar.com')
        dao_add_user_to_service(service, user, permissions=[])

        data = {
            'url': 'https://anotherurl.com',
        }
        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', f'Bearer {create_access_token(user)}')],
        )
        assert response.status_code == 403

    def test_should_return_403_when_updating_queue_callback_and_not_admin(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service, callback_channel=QUEUE_CHANNEL_TYPE)
        data = {
            'url': 'https://anotherurl.com',
        }
        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )
        assert response.status_code == 403

    def test_update_service_callback_should_allow_change_from_queue_to_webhook_by_user(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service, callback_channel=QUEUE_CHANNEL_TYPE)
        data = {
            'url': 'https://anotherurl.com',
            'bearer_token': 'some-token',
            'callback_channel': WEBHOOK_CHANNEL_TYPE,
        }
        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )
        assert response.status_code == 200
        assert response.json['data']['callback_channel'] == WEBHOOK_CHANNEL_TYPE
        assert service_callback_api.callback_channel == WEBHOOK_CHANNEL_TYPE

    def test_returns_403_when_changing_callback_to_queue_and_not_admin(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service, callback_channel=WEBHOOK_CHANNEL_TYPE)
        data = {
            'url': 'https://anotherurl.com',
            'callback_channel': QUEUE_CHANNEL_TYPE,
        }
        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )
        assert response.status_code == 403

    def test_should_return_404_when_trying_to_update_callback_from_different_service(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        another_service = sample_service(service_name=f'Another Service {uuid4()}')
        service_callback_api = sample_service_callback(another_service)
        data = {
            'url': 'https://anotherurl.com',
        }
        response = client.post(
            url_for(
                'service_callback.update_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            data=json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Authorization', f'Bearer {create_access_token(service.users[0])}'),
            ],
        )
        assert response.status_code == 404


class TestRemoveServiceCallback:
    @pytest.mark.idparametrize(('callback_channel'), {'webhook': (WEBHOOK_CHANNEL_TYPE), 'queue': (QUEUE_CHANNEL_TYPE)})
    def test_delete_service_callback_works_for_user(
        self,
        client,
        notify_db_session,
        sample_service_callback,
        sample_service,
        callback_channel,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service, callback_channel=callback_channel)

        response = client.delete(
            url_for(
                'service_callback.remove_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            headers=[('Authorization', f'Bearer {create_access_token(service.users[0])}')],
        )

        assert response.status_code == 204

        # DB verification
        stmt = select(ServiceCallback).where(ServiceCallback.service_id == service.id)
        assert len(notify_db_session.session.execute(stmt).all()) == 0

    def test_delete_service_callback_should_return_404_if_callback_does_not_exist(self, client, sample_service):
        service = sample_service()
        response = client.delete(
            url_for('service_callback.remove_service_callback', service_id=service.id, callback_id=str(uuid4())),
            headers=[('Authorization', f'Bearer {create_access_token(service.users[0])}')],
        )
        assert response.status_code == 404

    def test_delete_service_callback_should_return_403_if_not_authorized(
        self,
        client,
        sample_service_callback,
        sample_service,
        sample_user,
    ):
        service = sample_service()
        service_callback_api = sample_service_callback(service)
        user = sample_user(email=f'foo{uuid4()}@bar.com')
        dao_add_user_to_service(service, user, permissions=[])
        response = client.delete(
            url_for(
                'service_callback.remove_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            headers=[('Authorization', f'Bearer {create_access_token(user)}')],
        )
        assert response.status_code == 403

    def test_should_return_404_if_trying_to_delete_callback_from_different_service(
        self,
        client,
        sample_service_callback,
        sample_service,
    ):
        service = sample_service()
        another_service = sample_service(service_name=f'Another Service {uuid4()}')
        service_callback_api = sample_service_callback(another_service)

        response = client.delete(
            url_for(
                'service_callback.remove_service_callback', service_id=service.id, callback_id=service_callback_api.id
            ),
            headers=[('Authorization', f'Bearer {create_access_token(service.users[0])}')],
        )
        assert response.status_code == 404
