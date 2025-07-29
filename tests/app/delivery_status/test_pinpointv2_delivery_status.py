import pytest
from flask import url_for


@pytest.mark.parametrize(
    'query_string',
    [
        ({'foo': 'bar'}, b'foo=bar'),
        ({}, b''),
        ({'foo': 'bar', 'baz': 'qux'}, b'foo=bar&baz=qux'),
    ],
)
def test_post_delivery_status(client, mocker, query_string):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')

    response = client.post(url_for('pinpoint_v2.handler', **query_string[0]), json={'key': 'value'})

    assert response.status_code == 200
    assert response.json == {'delivery-status': {'key': 'value'}}

    actual = mock_logger.call_args_list[0].args[0]
    expected = 'PinpointV2 delivery-status request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'
