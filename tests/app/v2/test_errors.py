import pytest
from flask import url_for
from sqlalchemy.exc import DataError


@pytest.fixture(scope='function')
def app_for_test(mocker):
    import flask
    from flask import Blueprint
    from app.authentication.auth import AuthError
    from app.v2.errors import BadRequestError, TooManyRequestsError, JobIncompleteError
    from app import init_app

    app = flask.Flask(__name__, static_folder=None)
    app.config['TESTING'] = True
    init_app(app)
    from app import statsd_client

    statsd_client.init_app(app)

    from app.v2.errors import register_errors

    blue = Blueprint('v2_under_test', __name__, url_prefix='/v2/under_test')

    @blue.route('/raise_auth_error', methods=['GET'])
    def raising_auth_error():
        raise AuthError('some message', 403)

    @blue.route('/raise_bad_request', methods=['GET'])
    def raising_bad_request():
        raise BadRequestError(message='you forgot the thing')

    @blue.route('/raise_too_many_requests', methods=['GET'])
    def raising_too_many_requests():
        raise TooManyRequestsError(sending_limit='452')

    @blue.route('/raise_validation_error', methods=['GET'])
    def raising_validation_error():
        from app.schema_validation import validate
        from app.v2.notifications.notification_schemas import post_sms_request

        validate({'template_id': 'bad_uuid'}, post_sms_request)

    @blue.route('raise_data_error', methods=['GET'])
    def raising_data_error():
        raise DataError('There was a db problem', 'params', 'orig')

    @blue.route('raise_job_incomplete_error', methods=['GET'])
    def raising_job_incomplete_error():
        raise JobIncompleteError('Raising job incomplete error')

    @blue.route('raise_exception', methods=['GET'])
    def raising_exception():
        raise AssertionError('Raising any old exception')

    register_errors(blue)
    app.register_blueprint(blue)

    return app


def test_auth_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_auth_error'))
            assert response.status_code == 403
            error = response.json
            assert error == {'status_code': 403, 'errors': [{'error': 'AuthError', 'message': 'some message'}]}


def test_bad_request_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_bad_request'))
            assert response.status_code == 400
            error = response.json
            assert error == {
                'status_code': 400,
                'errors': [{'error': 'BadRequestError', 'message': 'you forgot the thing'}],
            }


def test_too_many_requests_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_too_many_requests'))
            assert response.status_code == 429
            error = response.json
            assert error == {
                'status_code': 429,
                'errors': [{'error': 'TooManyRequestsError', 'message': 'Exceeded send limits (452) for today'}],
            }


def test_validation_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_validation_error'))
            assert response.status_code == 400
            error = response.json
            assert len(error.keys()) == 2
            assert error['status_code'] == 400
            assert len(error['errors']) == 2
            assert {
                'error': 'ValidationError',
                'message': 'Please provide either a phone number or recipient identifier.',
            } in error['errors']
            assert {'error': 'ValidationError', 'message': 'template_id is not a valid UUID'} in error['errors']


def test_data_errors(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_data_error'))
            assert response.status_code == 404
            error = response.json
            assert error == {'status_code': 404, 'errors': [{'error': 'DataError', 'message': 'No result found'}]}


def test_job_incomplete_errors(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_job_incomplete_error'))
            assert response.status_code == 500
            error = response.json
            assert error == {
                'status_code': 500,
                'errors': [{'error': 'JobIncompleteError', 'message': 'Raising job incomplete error'}],
            }


def test_internal_server_error_handler(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_exception'))
            assert response.status_code == 500
            error = response.json
            assert error == {'message': 'Internal server error', 'result': 'error'}


def test_bad_method(app_for_test):
    """
    app/__init__.py does not define an error handler for "method not allowed" (405).  The
    body of the response, if any, will be the Flask default.
    """

    with app_for_test.test_request_context(), app_for_test.test_client() as client:
        response = client.post(url_for('v2_under_test.raising_exception'))
        assert response.status_code == 405
