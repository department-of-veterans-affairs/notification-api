from datetime import datetime, timedelta, timezone

from unittest.mock import patch

import pytest

from app.celery.twilio_tasks import _get_notifications, update_twilio_status
from app.constants import (
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_PREFERENCES_DECLINED,
)


@pytest.mark.parametrize(
    'status, expected',
    [
        (NOTIFICATION_CREATED, True),
        (NOTIFICATION_SENDING, True),
        (NOTIFICATION_SENT, False),
        (NOTIFICATION_DELIVERED, False),
        (NOTIFICATION_TECHNICAL_FAILURE, False),
        (NOTIFICATION_TEMPORARY_FAILURE, False),
        (NOTIFICATION_PERMANENT_FAILURE, False),
        (NOTIFICATION_PREFERENCES_DECLINED, False),
    ],
)
def test__get_notifications_statuses(sample_notification, status, expected):
    created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    notification = sample_notification(created_at=created_at, status=status, sent_by='twilio')

    notifications = _get_notifications()
    notification_ids = [n.id for n in notifications]
    if expected:
        assert notification.id in notification_ids
    else:
        assert notification.id not in notification_ids


@pytest.mark.parametrize(
    'minute_offset, expected',
    [
        (5, True),
        (30, True),
        (61, False),
        (180, False),
    ],
)
def test__get_notifications_datefilter(sample_notification, minute_offset, expected):
    created_at = datetime.now(timezone.utc) - timedelta(minutes=minute_offset)
    notification = sample_notification(created_at=created_at, status=NOTIFICATION_CREATED, sent_by='twilio')

    notifications = _get_notifications()
    notification_ids = [n.id for n in notifications]
    if expected:
        assert notification.id in notification_ids
    else:
        assert notification.id not in notification_ids


def test_update_twilio_status_with_results(mocker, sample_notification):
    notification = sample_notification(status=NOTIFICATION_CREATED, sent_by='twilio')

    mocker.patch('app.celery.twilio_tasks._get_notifications', return_value=[notification])

    with patch(
        'app.celery.twilio_tasks.twilio_sms_client.update_notification_status_override'
    ) as mock_update_notification_status_override:
        update_twilio_status()

    mock_update_notification_status_override.assert_called_once_with(notification.reference)


def test_update_twilio_status_no_results(mocker):
    mocker.patch('app.celery.twilio_tasks._get_notifications', return_value=[])

    with patch(
        'app.celery.twilio_tasks.twilio_sms_client.update_notification_status_override'
    ) as mock_update_notification_status_override:
        update_twilio_status()

    mock_update_notification_status_override.assert_not_called()
