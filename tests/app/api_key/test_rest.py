from app import DATETIME_FORMAT
from datetime import datetime
from tests.app.db import create_notification


def test_get_api_key_stats_with_sends(notify_db_session, admin_request, sample_email_template_history, sample_api_key):
    total_sends = 10
    notifications = [
        create_notification(template=sample_email_template_history, api_key=sample_api_key) for _ in range(total_sends)
    ]

    api_key_stats = admin_request.get(
        'api_key.get_api_key_stats',
        api_key_id=sample_api_key.id
    )['data']

    try:
        assert api_key_stats["api_key_id"] == str(sample_api_key.id)
        assert api_key_stats["email_sends"] == total_sends
        assert api_key_stats["sms_sends"] == 0
        assert api_key_stats["total_sends"] == total_sends

        # Test that a send has occurred within the last second.
        last_send_dt = datetime.strptime(api_key_stats["last_send"], DATETIME_FORMAT)
        now = datetime.utcnow()
        time_delta = now - last_send_dt
        assert abs(time_delta.total_seconds()) < 1
    finally:
        # Test clean-up
        for notification in notifications:
            notify_db_session.session.delete(notification)
        notify_db_session.session.commit()


def test_get_api_key_stats_no_sends(notify_db_session, admin_request, sample_api_key):
    # Add the session-scoped fixture to the function session.
    notify_db_session.session.add(sample_api_key)

    api_key_stats = admin_request.get(
        'api_key.get_api_key_stats',
        api_key_id=sample_api_key.id
    )['data']

    assert api_key_stats["api_key_id"] == str(sample_api_key.id)
    assert api_key_stats["email_sends"] == 0
    assert api_key_stats["sms_sends"] == 0
    assert api_key_stats["total_sends"] == 0
    assert api_key_stats["last_send"] is None


def test_get_api_keys_ranked(
    notify_db_session,
    admin_request,
    sample_service,
    sample_api_key,
    sample_api_key_function_with_session_service,
    sample_email_template_history
):
    # Add session-scoped fixtures to the function session.
    notify_db_session.session.add(sample_service)
    notify_db_session.session.add(sample_api_key)
    notify_db_session.session.add(sample_email_template_history)
    total_sends = 10

    notifications = [create_notification(template=sample_email_template_history, api_key=sample_api_key)]
    for _ in range(total_sends):
        notifications.append(create_notification(template=sample_email_template_history, api_key=sample_api_key))
        notifications.append(
            create_notification(
                template=sample_email_template_history,
                api_key=sample_api_key_function_with_session_service
            )
        )

    api_keys_ranked = admin_request.get(
        'api_key.get_api_keys_ranked',
        n_days_back=2
    )['data']

    try:
        assert api_keys_ranked[0]["api_key_name"] == sample_api_key.name
        assert api_keys_ranked[0]["service_name"] == sample_service.name
        assert api_keys_ranked[0]["sms_notifications"] == 0
        assert api_keys_ranked[0]["email_notifications"] == total_sends + 1
        assert api_keys_ranked[0]["total_notifications"] == total_sends + 1
        assert "last_notification_created" in api_keys_ranked[0]

        assert api_keys_ranked[1]["api_key_name"] == sample_api_key_function_with_session_service.name
        assert api_keys_ranked[1]["service_name"] == sample_service.name
        assert api_keys_ranked[1]["sms_notifications"] == 0
        assert api_keys_ranked[1]["email_notifications"] == total_sends
        assert api_keys_ranked[1]["total_notifications"] == total_sends
        assert "last_notification_created" in api_keys_ranked[0]
    finally:
        # Test clean-up
        for notification in notifications:
            notify_db_session.session.delete(notification)
        notify_db_session.session.commit()
