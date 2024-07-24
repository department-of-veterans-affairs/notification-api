from flask import url_for


def test_it_get_internal(client):
    response = client.get(url_for('internal.handler', generic='foo'))
    assert response.status_code == 200
    assert response.data == b'GET request received for endpoint /internal/foo?'


def test_it_get_with_query_string(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')
    client.get(url_for('internal.handler', generic='foobar', foo='bar'))

    actual = mock_logger.call_args_list[0].args[0]
    expected = 'Generic Internal Request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'

    actual = mock_logger.call_args_list[0].args[1]
    assert 'METHOD: GET' in actual, 'The logger was not called with the expected message.'
    assert 'ROOT_PATH: ' in actual, 'The logger was not called with the expected message.'
    assert 'PATH: /internal/foobar' in actual, 'The logger was not called with the expected message.'
    assert "QUERY_STRING: b'foo=bar' in actual, 'The logger was not called with the expected message."
    assert 'URL_RULE: /internal/<generic>' in actual, 'The logger was not called with the expected message.'
    assert 'TRACE_ID: None' in actual, 'The logger was not called with the expected message.'


def test_it_logging(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')
    client.post(url_for('internal.handler', generic='blah'), json={'key': 'value'})
    actual = mock_logger.call_args_list[0].args[0]
    expected = 'Generic Internal Request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'

    actual = mock_logger.call_args_list[0].args[1]
    assert 'METHOD: POST' in actual, 'The logger was not called with the expected message.'
    assert 'ROOT_PATH: ' in actual, 'The logger was not called with the expected message.'
    assert 'PATH: /internal/blah' in actual, 'The logger was not called with the expected message.'
    assert "QUERY_STRING: b'' in actual, 'The logger was not called with the expected message."
    assert 'URL_RULE: /internal/<generic>' in actual, 'The logger was not called with the expected message.'
    assert 'TRACE_ID: None' in actual, 'The logger was not called with the expected message.'


def test_it_post_internal(client):
    response = client.post(url_for('internal.handler', generic='bar'), json={'key': 'value'})
    assert response.status_code == 200
    assert response.json == {'bar': {'key': 'value'}}


def test_it_post_with_query_string(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')
    client.post(url_for('internal.handler', generic='foobar', foo='bar'), json={'key': 'value'})

    actual = mock_logger.call_args_list[0].args[0]
    expected = 'Generic Internal Request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'

    actual = mock_logger.call_args_list[0].args[1]
    assert 'METHOD: POST' in actual, 'The logger was not called with the expected message.'
    assert 'ROOT_PATH: ' in actual, 'The logger was not called with the expected message.'
    assert 'PATH: /internal/foobar' in actual, 'The logger was not called with the expected message.'
    assert "QUERY_STRING: b'foo=bar' in actual, 'The logger was not called with the expected message."
    assert 'URL_RULE: /internal/<generic>' in actual, 'The logger was not called with the expected message.'
    assert 'TRACE_ID: None' in actual, 'The logger was not called with the expected message.'
