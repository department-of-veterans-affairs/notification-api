"""
Integration tests for custom callback headers feature (ADR-001).

These tests verify the full chain wiring from data setup through to the outbound HTTP
callback, using a real database, real encryption, and requests_mock to capture final
outbound requests. They cover both callback paths:

1. Service-level: ServiceCallback with callback_headers → send_delivery_status_to_service
   → WebhookCallbackStrategy.send_callback → outbound POST with merged headers

2. Notification-level: Notification with callback_url + callback_headers →
   check_and_queue_notification_callback_task → send_delivery_status_from_notification
   → outbound POST with merged headers
"""

import json
from datetime import datetime
from uuid import uuid4

import pytest
import requests_mock

from app import encryption
from app.callback.webhook_callback_strategy import generate_callback_signature
from app.celery.service_callback_tasks import (
    check_and_queue_callback_task,
    check_and_queue_notification_callback_task,
    create_delivery_status_callback_data,
    send_delivery_status_from_notification,
    send_delivery_status_to_service,
)
from app.constants import (
    DATETIME_FORMAT,
    DELIVERY_STATUS_CALLBACK_TYPE,
    EMAIL_TYPE,
    SMS_TYPE,
)
from tests.app.db import create_service_callback_api


# ---------------------------------------------------------------------------
# Service-level callback path integration tests
# ---------------------------------------------------------------------------


class TestServiceLevelCallbackHeadersIntegration:
    """Tests that verify callback_headers on ServiceCallback flow through
    the entire service-level callback chain to the outbound HTTP request."""

    def test_service_callback_with_custom_headers_delivers_headers_in_outbound_request(
        self,
        sample_service,
        sample_template,
        sample_notification,
    ):
        """Full chain: ServiceCallback(callback_headers) → encrypt status →
        send_delivery_status_to_service → WebhookCallbackStrategy → outbound POST."""
        service = sample_service(restricted=True)
        template = sample_template(service=service, template_type=EMAIL_TYPE, subject='Test')

        custom_headers = {'X-Api-Key': 'team-secret-123', 'X-Correlation-Id': 'corr-abc'}
        callback_api = create_service_callback_api(
            service=service,
            url='https://callback.example.com/status',
            bearer_token='svc-bearer-token',
            callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
            callback_headers=custom_headers,
        )

        datestr = datetime(2024, 1, 15, 12, 0, 0)
        notification = sample_notification(
            template=template,
            created_at=datestr,
            updated_at=datestr,
            sent_at=datestr,
            status='delivered',
        )

        encrypted_status_update = create_delivery_status_callback_data(notification, callback_api)

        with requests_mock.Mocker() as rmock:
            rmock.post(callback_api.url, json={}, status_code=200)
            send_delivery_status_to_service(
                callback_api.id, notification.id, encrypted_status_update=encrypted_status_update
            )

            assert rmock.call_count == 1
            sent_headers = rmock.request_history[0].headers

            # Custom headers are present
            assert sent_headers['X-Api-Key'] == 'team-secret-123'
            assert sent_headers['X-Correlation-Id'] == 'corr-abc'

            # System headers are present and unmodified
            assert sent_headers['Content-Type'] == 'application/json'
            assert sent_headers['Authorization'] == 'Bearer svc-bearer-token'

    def test_service_callback_without_custom_headers_delivers_only_system_headers(
        self,
        sample_service,
        sample_template,
        sample_notification,
    ):
        """Baseline: no callback_headers → only system headers in outbound POST."""
        service = sample_service(restricted=True)
        template = sample_template(service=service, template_type=SMS_TYPE)

        callback_api = create_service_callback_api(
            service=service,
            url='https://callback.example.com/status',
            bearer_token='svc-bearer-only',
            callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
        )

        datestr = datetime(2024, 1, 15, 12, 0, 0)
        notification = sample_notification(
            template=template,
            created_at=datestr,
            updated_at=datestr,
            sent_at=datestr,
            status='sent',
        )

        encrypted_status_update = create_delivery_status_callback_data(notification, callback_api)

        with requests_mock.Mocker() as rmock:
            rmock.post(callback_api.url, json={}, status_code=200)
            send_delivery_status_to_service(
                callback_api.id, notification.id, encrypted_status_update=encrypted_status_update
            )

            assert rmock.call_count == 1
            sent_headers = rmock.request_history[0].headers

            # System headers
            assert sent_headers['Content-Type'] == 'application/json'
            assert sent_headers['Authorization'] == 'Bearer svc-bearer-only'

            # No custom headers
            assert 'X-Api-Key' not in sent_headers
            assert 'X-Correlation-Id' not in sent_headers

    def test_service_callback_custom_headers_cannot_override_system_headers(
        self,
        sample_service,
        sample_template,
        sample_notification,
    ):
        """Blocked headers: custom headers that match system header names are filtered out."""
        service = sample_service(restricted=True)
        template = sample_template(service=service, template_type=EMAIL_TYPE, subject='Test')

        # Attempt to override system headers
        custom_headers = {
            'Authorization': 'Bearer evil-token',
            'Content-Type': 'text/plain',
            'X-Legit-Header': 'allowed-value',
        }
        callback_api = create_service_callback_api(
            service=service,
            url='https://callback.example.com/status',
            bearer_token='real-token',
            callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
            callback_headers=custom_headers,
        )

        datestr = datetime(2024, 1, 15, 12, 0, 0)
        notification = sample_notification(
            template=template,
            created_at=datestr,
            updated_at=datestr,
            sent_at=datestr,
            status='delivered',
        )

        encrypted_status_update = create_delivery_status_callback_data(notification, callback_api)

        with requests_mock.Mocker() as rmock:
            rmock.post(callback_api.url, json={}, status_code=200)
            send_delivery_status_to_service(
                callback_api.id, notification.id, encrypted_status_update=encrypted_status_update
            )

            assert rmock.call_count == 1
            sent_headers = rmock.request_history[0].headers

            # System headers NOT overridden
            assert sent_headers['Content-Type'] == 'application/json'
            assert sent_headers['Authorization'] == 'Bearer real-token'

            # Legitimate custom header IS present
            assert sent_headers['X-Legit-Header'] == 'allowed-value'

    def test_service_callback_headers_survive_encryption_roundtrip(
        self,
        sample_service,
        sample_template,
        sample_notification,
    ):
        """Verify headers are correctly encrypted at rest and decrypted for outbound delivery."""
        service = sample_service(restricted=True)
        template = sample_template(service=service, template_type=SMS_TYPE)

        original_headers = {
            'X-Webhook-Secret': 'super-secret-value-!@#$%',
            'X-Request-Source': 'va-notify',
        }
        callback_api = create_service_callback_api(
            service=service,
            url='https://callback.example.com/status',
            bearer_token='bearer-for-roundtrip',
            callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
            callback_headers=original_headers,
        )

        # Verify headers are encrypted in the database (raw column is not plaintext)
        assert callback_api._callback_headers is not None
        assert callback_api._callback_headers != json.dumps(original_headers)

        # Verify decryption returns original headers
        decrypted = encryption.decrypt(callback_api._callback_headers)
        assert decrypted == original_headers

        # Verify full delivery chain
        datestr = datetime(2024, 1, 15, 12, 0, 0)
        notification = sample_notification(
            template=template,
            created_at=datestr,
            updated_at=datestr,
            sent_at=datestr,
            status='delivered',
        )

        encrypted_status_update = create_delivery_status_callback_data(notification, callback_api)

        with requests_mock.Mocker() as rmock:
            rmock.post(callback_api.url, json={}, status_code=200)
            send_delivery_status_to_service(
                callback_api.id, notification.id, encrypted_status_update=encrypted_status_update
            )

            sent_headers = rmock.request_history[0].headers
            assert sent_headers['X-Webhook-Secret'] == 'super-secret-value-!@#$%'
            assert sent_headers['X-Request-Source'] == 'va-notify'

    def test_service_callback_payload_integrity_with_custom_headers(
        self,
        sample_service,
        sample_template,
        sample_notification,
    ):
        """Verify that adding custom headers doesn't affect the JSON payload."""
        service = sample_service(restricted=True)
        template = sample_template(service=service, template_type=EMAIL_TYPE, subject='Test')

        callback_api = create_service_callback_api(
            service=service,
            url='https://callback.example.com/status',
            bearer_token='payload-check-token',
            callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
            callback_headers={'X-Extra': 'value'},
        )

        datestr = datetime(2024, 1, 15, 12, 0, 0)
        notification = sample_notification(
            template=template,
            created_at=datestr,
            updated_at=datestr,
            sent_at=datestr,
            status='sent',
        )

        encrypted_status_update = create_delivery_status_callback_data(notification, callback_api)

        with requests_mock.Mocker() as rmock:
            rmock.post(callback_api.url, json={}, status_code=200)
            send_delivery_status_to_service(
                callback_api.id, notification.id, encrypted_status_update=encrypted_status_update
            )

            payload = json.loads(rmock.request_history[0].text)
            assert payload['id'] == str(notification.id)
            assert payload['status'] == 'sent'
            assert payload['notification_type'] == EMAIL_TYPE
            assert payload['created_at'] == datestr.strftime(DATETIME_FORMAT)


# ---------------------------------------------------------------------------
# Notification-level callback path integration tests
# ---------------------------------------------------------------------------


class TestNotificationLevelCallbackHeadersIntegration:
    """Tests that verify callback_headers on Notification flow through
    the notification-level callback chain to the outbound HTTP request."""

    def test_notification_callback_with_custom_headers_delivers_headers(
        self,
        sample_notification,
        mocker,
    ):
        """Full chain: Notification(callback_url, callback_headers) →
        check_and_queue_notification_callback_task captures kwargs →
        send_delivery_status_from_notification → outbound POST with custom headers."""
        custom_headers = {'X-Api-Key': 'notif-key-456', 'X-Source': 'va-notify'}
        callback_url = 'https://notif-callback.example.com/delivery'

        notification = sample_notification(
            callback_url=callback_url,
            callback_headers=custom_headers,
            status='delivered',
        )

        # Capture the apply_async call to get kwargs
        mock_apply_async = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_from_notification.apply_async'
        )

        check_and_queue_notification_callback_task(notification)

        # Extract the kwargs that would be passed to send_delivery_status_from_notification
        assert mock_apply_async.call_count == 1
        call_kwargs = mock_apply_async.call_args[1]['kwargs']
        assert call_kwargs['callback_url'] == callback_url
        assert 'encrypted_callback_headers' in call_kwargs

        # Now invoke the celery task directly with captured kwargs
        with requests_mock.Mocker() as rmock:
            rmock.post(callback_url, json={}, status_code=200)
            send_delivery_status_from_notification(
                callback_signature=call_kwargs['callback_signature'],
                callback_url=call_kwargs['callback_url'],
                notification_data=call_kwargs['notification_data'],
                notification_id=call_kwargs['notification_id'],
                encrypted_callback_headers=call_kwargs['encrypted_callback_headers'],
            )

            assert rmock.call_count == 1
            sent_headers = rmock.request_history[0].headers

            # Custom headers present
            assert sent_headers['X-Api-Key'] == 'notif-key-456'
            assert sent_headers['X-Source'] == 'va-notify'

            # System headers present
            assert sent_headers['Content-Type'] == 'application/json'
            assert 'x-enp-signature' in sent_headers

    def test_notification_callback_without_custom_headers_omits_encrypted_kwarg(
        self,
        sample_notification,
        mocker,
    ):
        """Verify that when no callback_headers are set, encrypted_callback_headers kwarg
        is omitted from the queued task."""
        callback_url = 'https://notif-callback.example.com/delivery'

        notification = sample_notification(
            callback_url=callback_url,
            status='delivered',
        )

        mock_apply_async = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_from_notification.apply_async'
        )

        check_and_queue_notification_callback_task(notification)

        call_kwargs = mock_apply_async.call_args[1]['kwargs']
        assert 'encrypted_callback_headers' not in call_kwargs

        # Invoke directly — no custom headers in outbound
        with requests_mock.Mocker() as rmock:
            rmock.post(callback_url, json={}, status_code=200)
            send_delivery_status_from_notification(
                callback_signature=call_kwargs['callback_signature'],
                callback_url=call_kwargs['callback_url'],
                notification_data=call_kwargs['notification_data'],
                notification_id=call_kwargs['notification_id'],
            )

            sent_headers = rmock.request_history[0].headers
            assert sent_headers['Content-Type'] == 'application/json'
            assert 'x-enp-signature' in sent_headers
            assert 'X-Api-Key' not in sent_headers

    def test_notification_callback_custom_headers_cannot_override_system_headers(
        self,
        sample_notification,
        mocker,
    ):
        """Custom headers on notification cannot override system Content-Type or x-enp-signature."""
        callback_url = 'https://notif-callback.example.com/delivery'
        custom_headers = {
            'Content-Type': 'text/plain',
            'x-enp-signature': 'fake-signature',
            'X-Allowed': 'good-value',
        }

        notification = sample_notification(
            callback_url=callback_url,
            callback_headers=custom_headers,
            status='delivered',
        )

        mock_apply_async = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_from_notification.apply_async'
        )

        check_and_queue_notification_callback_task(notification)

        call_kwargs = mock_apply_async.call_args[1]['kwargs']

        with requests_mock.Mocker() as rmock:
            rmock.post(callback_url, json={}, status_code=200)
            send_delivery_status_from_notification(
                callback_signature=call_kwargs['callback_signature'],
                callback_url=call_kwargs['callback_url'],
                notification_data=call_kwargs['notification_data'],
                notification_id=call_kwargs['notification_id'],
                encrypted_callback_headers=call_kwargs['encrypted_callback_headers'],
            )

            sent_headers = rmock.request_history[0].headers

            # System headers NOT overridden
            assert sent_headers['Content-Type'] == 'application/json'
            assert sent_headers['x-enp-signature'] == call_kwargs['callback_signature']

            # Allowed custom header IS present
            assert sent_headers['X-Allowed'] == 'good-value'

    def test_notification_callback_headers_survive_encryption_roundtrip(
        self,
        sample_notification,
        mocker,
    ):
        """Verify headers encrypted on Notification model are decrypted correctly for outbound delivery."""
        original_headers = {
            'X-Hmac-Signature': 'sha256=abc123def456',
            'X-Request-Id': str(uuid4()),
        }
        callback_url = 'https://notif-callback.example.com/delivery'

        notification = sample_notification(
            callback_url=callback_url,
            callback_headers=original_headers,
            status='delivered',
        )

        # Verify the model encrypted the headers
        assert notification._callback_headers is not None
        decrypted = encryption.decrypt(notification._callback_headers)
        assert decrypted == original_headers

        mock_apply_async = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_from_notification.apply_async'
        )

        check_and_queue_notification_callback_task(notification)
        call_kwargs = mock_apply_async.call_args[1]['kwargs']

        with requests_mock.Mocker() as rmock:
            rmock.post(callback_url, json={}, status_code=200)
            send_delivery_status_from_notification(
                callback_signature=call_kwargs['callback_signature'],
                callback_url=call_kwargs['callback_url'],
                notification_data=call_kwargs['notification_data'],
                notification_id=call_kwargs['notification_id'],
                encrypted_callback_headers=call_kwargs['encrypted_callback_headers'],
            )

            sent_headers = rmock.request_history[0].headers
            assert sent_headers['X-Hmac-Signature'] == 'sha256=abc123def456'
            assert sent_headers['X-Request-Id'] == original_headers['X-Request-Id']


# ---------------------------------------------------------------------------
# Routing integration tests (check_and_queue_callback_task)
# ---------------------------------------------------------------------------


class TestCallbackRoutingIntegration:
    """Tests that verify check_and_queue_callback_task routes to the correct
    callback path based on whether the notification has a callback_url."""

    def test_notification_with_callback_url_routes_to_notification_path(
        self,
        sample_notification,
        mocker,
    ):
        """When notification has callback_url, check_and_queue_callback_task uses
        the notification-level path (not the service-level path)."""
        notification = sample_notification(
            callback_url='https://notif-callback.example.com/delivery',
            callback_headers={'X-Custom': 'value'},
            status='delivered',
        )

        mock_notification_path = mocker.patch(
            'app.celery.service_callback_tasks.check_and_queue_notification_callback_task'
        )
        mock_service_path = mocker.patch(
            'app.celery.service_callback_tasks.check_and_queue_service_callback_task'
        )

        check_and_queue_callback_task(notification)

        mock_notification_path.assert_called_once_with(notification)
        mock_service_path.assert_not_called()

    def test_notification_without_callback_url_routes_to_service_path(
        self,
        sample_notification,
        mocker,
    ):
        """When notification has no callback_url, check_and_queue_callback_task uses
        the service-level path."""
        notification = sample_notification(status='delivered')

        mock_notification_path = mocker.patch(
            'app.celery.service_callback_tasks.check_and_queue_notification_callback_task'
        )
        mock_service_path = mocker.patch(
            'app.celery.service_callback_tasks.check_and_queue_service_callback_task'
        )

        check_and_queue_callback_task(notification)

        mock_service_path.assert_called_once_with(notification, None)
        mock_notification_path.assert_not_called()

    def test_full_service_level_chain_with_routing(
        self,
        sample_service,
        sample_template,
        sample_notification,
        mocker,
    ):
        """End-to-end: notification without callback_url triggers service-level
        callback that includes custom headers from ServiceCallback."""
        service = sample_service(restricted=True)
        template = sample_template(service=service, template_type=EMAIL_TYPE, subject='Test')

        custom_headers = {'X-Team-Id': 'team-42'}
        create_service_callback_api(
            service=service,
            url='https://service-callback.example.com/status',
            bearer_token='svc-token',
            callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
            callback_headers=custom_headers,
        )

        datestr = datetime(2024, 1, 15, 12, 0, 0)
        notification = sample_notification(
            template=template,
            created_at=datestr,
            updated_at=datestr,
            sent_at=datestr,
            status='delivered',
        )

        # Mock the celery apply_async to capture args
        mock_apply_async = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
        )

        check_and_queue_callback_task(notification)

        # Verify the service-level path was triggered
        assert mock_apply_async.call_count == 1
        call_kwargs = mock_apply_async.call_args[1]['kwargs']
        assert 'service_callback_id' in call_kwargs
        assert 'encrypted_status_update' in call_kwargs

    def test_notification_level_headers_are_independent_of_service_callback_headers(
        self,
        sample_service,
        sample_template,
        sample_notification,
        mocker,
    ):
        """When notification has callback_url + callback_headers AND service has a
        ServiceCallback with different headers, only the notification-level headers
        are used (notification-level replaces service-level entirely)."""
        service = sample_service(restricted=True)
        template = sample_template(service=service, template_type=EMAIL_TYPE, subject='Test')

        # Service-level callback with one set of headers
        create_service_callback_api(
            service=service,
            url='https://service-callback.example.com/status',
            bearer_token='svc-token',
            callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
            callback_headers={'X-Service-Header': 'svc-value'},
        )

        # Notification with different callback_url and headers
        notif_callback_url = 'https://notif-callback.example.com/delivery'
        notif_headers = {'X-Notif-Header': 'notif-value'}

        notification = sample_notification(
            template=template,
            callback_url=notif_callback_url,
            callback_headers=notif_headers,
            status='delivered',
        )

        mock_apply_async = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_from_notification.apply_async'
        )

        check_and_queue_callback_task(notification)

        # Notification-level path used
        assert mock_apply_async.call_count == 1
        call_kwargs = mock_apply_async.call_args[1]['kwargs']
        assert call_kwargs['callback_url'] == notif_callback_url

        # Invoke the task and verify only notification-level headers appear
        with requests_mock.Mocker() as rmock:
            rmock.post(notif_callback_url, json={}, status_code=200)
            send_delivery_status_from_notification(
                callback_signature=call_kwargs['callback_signature'],
                callback_url=call_kwargs['callback_url'],
                notification_data=call_kwargs['notification_data'],
                notification_id=call_kwargs['notification_id'],
                encrypted_callback_headers=call_kwargs['encrypted_callback_headers'],
            )

            sent_headers = rmock.request_history[0].headers
            # Notification-level custom header present
            assert sent_headers['X-Notif-Header'] == 'notif-value'
            # Service-level header NOT present
            assert 'X-Service-Header' not in sent_headers
