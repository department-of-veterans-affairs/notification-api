import pytest

from app.celery.process_ga4_measurement_tasks import post_to_ga4


@pytest.fixture
def valid_data():
    return {
        'notification_id': 'e774d2a6-4946-41b5-841a-7ac6a42d178b',
        'template_name': 'hi',
        'template_id': 'e774d2a6-4946-41b5-841a-7ac6a42d178b',
        'service_id': 'e774d2a6-4946-41b5-841a-7ac6a42d178b',
        'service_name': 'test',
        'client_id': 'vanotify',
        'name': 'email_open',
        'source': 'vanotify',
        'medium': 'email',
    }


def test_post_to_ga4_with_valid_data(valid_data):
    response = post_to_ga4(
        valid_data['notification_id'],
        valid_data['template_name'],
        valid_data['template_id'],
        valid_data['service_id'],
        valid_data['service_name'],
        client_id=valid_data['client_id'],
        name=valid_data['name'],
        source=valid_data['source'],
        medium=valid_data['medium'],
    )
    assert response
