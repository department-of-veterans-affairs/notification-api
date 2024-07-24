from flask import url_for


def test_get_internal(client):
    response = client.get(url_for('internal.handler', generic='blah'))
    assert response.status_code == 200
    assert response.data == b'GET request received for endpoint /internal/blah?'


def test_post_internal(client):
    response = client.post(url_for('internal.handler', generic='blah'), json={'key': 'value'})
    assert response.status_code == 200
    assert response.json == {'request_received': {'key': 'value'}}


def test_logging(client, mocker):
    mock_logger = mocker.patch('app.internal.rest.current_app.logger')
    client.post(url_for('internal.handler', generic='blah'), json={'key': 'value'})

    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'ROOT_PATH', '')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'METHOD', 'POST')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'PATH', '/internal/blah')
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'JSON', {'key': 'value'})
    mock_logger.info.assert_any_call('Generic Internal Request %s: %s', 'TRACE_ID', None)
