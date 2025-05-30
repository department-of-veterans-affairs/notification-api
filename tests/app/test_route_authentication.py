from unittest.mock import patch
import uuid

from flask import url_for
from werkzeug.routing import UUIDConverter, UnicodeConverter, IntegerConverter, PathConverter


def test_all_routes_have_authentication(client, mocker):
    # Redis adds +25 seconds to this check for no reason, we are not checking redis in this test
    mocker.patch('app.status.healthcheck.redis_check', return_value=None)
    routes_without_authentication = set()
    # Populate the set with routes that do not enforce authentication.
    for rule in client.application.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue

        for method in rule.methods:
            if method == 'OPTIONS':
                continue

            make_request = getattr(client, method.lower())
            # Mock time.sleep to return immediately
            with patch('time.sleep', return_value=None):
                with patch('app.googleanalytics.ga4.post_to_ga4.delay'):
                    response = make_request(_build_url(rule))

            if response.status_code not in (401, 403):
                routes_without_authentication.add(str(rule))

    expected_routes_without_authentication = (
        '/',
        '/_status',
        '/_status/live-service-and-organisation-counts',
        '/ga4/open-email-tracking/<notification_id>',
        '/internal/<generic>',
        '/internal/sleep',
        '/internal/502',
        '/platform-stats/monthly',
    )

    for route in routes_without_authentication:
        assert route in expected_routes_without_authentication


def _build_url(rule):
    example_path_variables = {
        UUIDConverter: uuid.uuid4(),
        UnicodeConverter: 'example-string',
        IntegerConverter: 1,
        PathConverter: '/',
    }

    params = {
        path_variable_name: example_path_variables[type(converter)]
        for path_variable_name, converter in rule._converters.items()
    }

    return url_for(rule.endpoint, **params)
