from unittest.mock import patch

from flask import url_for
import pytest


# Parameterize for generic_one and generic_two
@pytest.mark.parametrize('endpoint', ['internal.generic_one', 'internal.generic_two'])
def test_internal_generic_with_valid_data(client, endpoint):
    """
    A POST request with valid data should receive a 200 response.
    """
    with patch('app.internal.rest.current_app.logger.info') as mock_logger:
        response = client.post(
            path=url_for(endpoint),
            json={'key': 'value'},
        )
    assert response.status_code == 200
    assert response.get_json() == {'message': 'Request received'}

    # Assert that the logger was called with the expected message.
    # There will be 2 logs, one for the incoming request and the one from the route.
    assert mock_logger.call_count >= 1
    assert mock_logger.call_args_list[0][0][0] == 'Received request: %s'
