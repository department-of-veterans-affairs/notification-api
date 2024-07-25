from flask import url_for


def test_it_get_internal(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')
    response = client.get(url_for('internal.handler', generic='foo'))
    assert response.status_code == 200
    assert response.data == b'GET request received for endpoint /internal/foo?'

    actual = mock_logger.call_args_list[0].args[0]
    expected = 'Generic Internal Request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'

    actual = mock_logger.call_args_list[0].args[1]
    assert 'METHOD: GET' in actual, 'The logged info did not contain METHOD.'
    assert 'ROOT_PATH: ' in actual, 'The logged info did not contain ROOT_PATH.'
    assert 'PATH: /internal/foo' in actual, 'The logged info did not contain PATH.'
    assert 'URL_RULE: /internal/<generic>' in actual, 'The logged info did not contain URL_RULE.'
    assert 'TRACE_ID: None' in actual, 'The logged info did not contain TRACE_ID.'
    assert 'HEADERS: ' in actual, 'The logged info did not contain HEADERS.'
    assert "QUERY_STRING: b''" in actual, 'The logged info did not contain QUERY_STRING.'


def test_it_get_internal_query_string(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')
    response = client.get(url_for('internal.handler', generic='foobar', foo='bar'))
    assert response.status_code == 200

    actual = mock_logger.call_args_list[0].args[0]
    expected = 'Generic Internal Request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'

    actual = mock_logger.call_args_list[0].args[1]
    assert 'METHOD: GET' in actual, 'The logged info did not contain METHOD.'
    assert 'ROOT_PATH: ' in actual, 'The logged info did not contain ROOT_PATH.'
    assert 'PATH: /internal/foobar' in actual, 'The logged info did not contain PATH.'
    assert "QUERY_STRING: b'foo=bar'" in actual, 'The logged info did not contain QUERY_STRING.'
    assert 'URL_RULE: /internal/<generic>' in actual, 'The logged info did not contain URL_RULE.'
    assert 'TRACE_ID: None' in actual, 'The logged info did not contain TRACE_ID.'
    assert 'HEADERS: ' in actual, 'The logged info did not contain HEADERS.'


def test_it_post_internal(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')
    response = client.post(url_for('internal.handler', generic='bar'), json={'key': 'value'})
    assert response.status_code == 200
    assert response.json == {'bar': {'key': 'value'}}

    actual = mock_logger.call_args_list[0].args[0]
    expected = 'Generic Internal Request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'

    actual = mock_logger.call_args_list[0].args[1]
    assert 'METHOD: POST' in actual, 'The logged info did not contain METHOD.'
    assert 'ROOT_PATH: ' in actual, 'The logged info did not contain ROOT_PATH.'
    assert 'PATH: /internal/bar' in actual, 'The logged info did not contain PATH.'
    assert 'URL_RULE: /internal/<generic>' in actual, 'The logged info did not contain URL_RULE.'
    assert 'TRACE_ID: None' in actual, 'The logged info did not contain TRACE_ID.'
    assert "JSON: {'key': 'value'}" in actual, 'The logged info did not contain JSON.'
    assert 'HEADERS: ' in actual, 'The logged info did not contain HEADERS.'
    assert "QUERY_STRING: b''" in actual, 'The logged info did not contain QUERY_STRING.'


def test_it_post_internal_query_string(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger.info')
    response = client.post(url_for('internal.handler', generic='foobar', foo='bar'), json={'key': 'value'})
    assert response.status_code == 200

    actual = mock_logger.call_args_list[0].args[0]
    expected = 'Generic Internal Request: %s'
    assert actual == expected, 'The logger was not called with the expected message.'

    actual = mock_logger.call_args_list[0].args[1]
    assert 'METHOD: POST' in actual, 'The logged info did not contain METHOD.'
    assert 'ROOT_PATH: ' in actual, 'The logged info did not contain ROOT_PATH.'
    assert 'PATH: /internal/foobar' in actual, 'The logged info did not contain PATH.'
    assert "QUERY_STRING: b'foo=bar'" in actual, 'The logged info did not contain QUERY_STRING.'
    assert 'URL_RULE: /internal/<generic>' in actual, 'The logged info did not contain URL_RULE.'
    assert 'TRACE_ID: None' in actual, 'The logged info did not contain TRACE_ID.'
    assert "JSON: {'key': 'value'}" in actual, 'The logged info did not contain JSON.'
    assert 'HEADERS: ' in actual, 'The logged info did not contain HEADERS.'
