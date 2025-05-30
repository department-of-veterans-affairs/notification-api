from flask import jsonify, current_app, request, json
from notifications_utils.recipients import InvalidEmailError, InvalidPhoneError
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from marshmallow import ValidationError
from jsonschema import ValidationError as JsonSchemaValidationError
from app.authentication.auth import AuthError
from app.exceptions import ArchiveValidationError


class VirusScanError(Exception):
    def __init__(
        self,
        message,
    ):
        super().__init__(message)


class InvalidRequest(Exception):
    code = None
    fields = []

    def __init__(
        self,
        message,
        status_code,
    ):
        super().__init__()
        self.message = message
        self.status_code = status_code

    def to_dict(self):
        return {'result': 'error', 'message': self.message}

    def to_dict_v2(self):
        """
        Version 2 of the public api error response.
        """
        return {
            'status_code': self.status_code,
            'errors': [{'error': self.__class__.__name__, 'message': self.message}],
        }

    def __str__(self):
        return str(self.to_dict())


def register_errors(blueprint):  # noqa: C901
    @blueprint.errorhandler(InvalidEmailError)
    def invalid_email_format(error):
        return jsonify(result='error', message=str(error)), 400

    @blueprint.errorhandler(InvalidPhoneError)
    def invalid_phone_format(error):
        return jsonify(result='error', message=str(error)), 400

    @blueprint.errorhandler(AuthError)
    def authentication_error(error):
        current_app.logger.info('API AuthError, client: %s error: %s', request.headers.get('User-Agent'), error)
        return jsonify(result='error', message=error.message), error.code

    @blueprint.errorhandler(ValidationError)
    def marshmallow_validation_error(error):
        current_app.logger.info(error)
        return jsonify(result='error', message=error.messages), 400

    @blueprint.errorhandler(JsonSchemaValidationError)
    def jsonschema_validation_error(error):
        current_app.logger.info(error)
        return jsonify(json.loads(error.message)), 400

    @blueprint.errorhandler(ArchiveValidationError)
    def archive_validation_error(error):
        current_app.logger.info(error)
        return jsonify(result='error', message=str(error)), 400

    @blueprint.errorhandler(InvalidRequest)
    def invalid_data(error):
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        current_app.logger.info(error)
        return response

    @blueprint.errorhandler(400)
    def bad_request(e):
        msg = e.description or 'Invalid request parameters'
        current_app.logger.exception(msg)
        return jsonify(result='error', message=str(msg)), 400

    @blueprint.errorhandler(401)
    def unauthorized(e):
        error_message = 'Unauthorized, authentication token must be provided'
        return jsonify(result='error', message=error_message), 401, [('WWW-Authenticate', 'Bearer')]

    @blueprint.errorhandler(403)
    def forbidden(e):
        error_message = 'Forbidden, invalid authentication token provided'
        return jsonify(result='error', message=error_message), 403

    @blueprint.errorhandler(429)
    def limit_exceeded(e):
        current_app.logger.exception(e)
        return jsonify(result='error', message=str(e.description)), 429

    @blueprint.errorhandler(NoResultFound)
    @blueprint.errorhandler(DataError)
    def no_result_found(e):
        current_app.logger.info(e)
        return jsonify(result='error', message='No result found'), 404

    @blueprint.errorhandler(NotImplementedError)
    def not_implemented(e):
        current_app.logger.exception(e)
        return jsonify(result='error', message='Not Implemented'), 501


def invalid_data_v2(error):
    response = jsonify(error.to_dict_v2())
    response.status_code = error.status_code
    current_app.logger.info(error)
    return response
