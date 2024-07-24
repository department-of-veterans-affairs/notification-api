from flask import url_for


def test_it_get_internal(client):
    response = client.get(url_for('internal.handler', generic='foo'))
    assert response.status_code == 200
    assert response.data == b'GET request received for endpoint /internal/foo?'


def test_it_get_with_query_string(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger')
    client.get(url_for('internal.handler', generic='foobar', foo='bar'))
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'ROOT_PATH', '')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'METHOD', 'GET')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'PATH', '/internal/foobar')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'TRACE_ID', None)
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'QUERY_STRING', b'foo=bar')


def test_it_logging(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger')
    client.post(url_for('internal.handler', generic='blah'), json={'key': 'value'})

    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'ROOT_PATH', '')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'METHOD', 'POST')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'PATH', '/internal/blah')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'JSON', {'key': 'value'})
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'TRACE_ID', None)


def test_it_post_internal(client):
    response = client.post(url_for('internal.handler', generic='bar'), json={'key': 'value'})
    assert response.status_code == 200
    assert response.json == {'bar': {'key': 'value'}}


def test_it_post_with_query_string(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger')
    client.post(url_for('internal.handler', generic='foobar', foo='bar'), json={'key': 'value'})
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'ROOT_PATH', '')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'METHOD', 'POST')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'PATH', '/internal/foobar')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'TRACE_ID', None)
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'QUERY_STRING', b'foo=bar')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'JSON', {'key': 'value'})
