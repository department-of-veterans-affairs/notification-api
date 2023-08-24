"""
Declare all error handlers for v3 in this file.  This ensures consistent error handling
across all v3 endpoints.
"""

from app.authentication.auth import AuthError
from flask import Blueprint, current_app, request
from jsonschema import ValidationError

# TODO
from flask import jsonify
from notifications_utils.recipients import InvalidEmailError
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.attachments.exceptions import UnsupportedMimeTypeException
from app.errors import InvalidRequest


v3_blueprint = Blueprint("v3", __name__, url_prefix='/v3')


########################################
# Error handlers common to all v3 routes
########################################

@v3_blueprint.errorhandler(AuthError)
def auth_error(error):
    current_app.logger.info("API AuthError, client: %s error: %s", request.headers.get("User-Agent"), error)
    return error.to_dict_v2(), error.code


@v3_blueprint.errorhandler(ValidationError)
def validation_error(error):
    current_app.logger.info(error)
    return {
        "errors": [
            {
                "error": "ValidationError",
                "message": error.message,
            }
        ]
    }, 400

#######################################################

class JobIncompleteError(Exception):
    def __init__(self, message):
        self.message = message
        self.status_code = 500

    def to_dict_v2(self):
        return {
            'status_code': self.status_code,
            "errors": [
                {
                    "error": 'JobIncompleteError',
                    "message": self.message
                }
            ]
        }


class TooManyRequestsError(InvalidRequest):
    status_code = 429
    message_template = 'Exceeded send limits ({}) for today'

    def __init__(self, sending_limit):
        self.message = self.message_template.format(sending_limit)


class RateLimitError(InvalidRequest):
    status_code = 429
    message_template = 'Exceeded rate limit for key type {} of {} requests per {} seconds'
    message_template_without_key_type = 'Exceeded rate limit of {} requests per {} seconds'

    def __init__(self, sending_limit, interval, key_type=None):
        # normal keys are spoken of as "live" in the documentation
        # so using this in the error messaging
        if key_type and key_type == 'normal':
            key_type = 'live'

        self.message = (
            self.message_template.format(key_type.upper(), sending_limit, interval)
            if key_type
            else self.message_template_without_key_type.format(sending_limit, interval)
        )


class BadRequestError(InvalidRequest):
    message = "An error occurred"

    def __init__(self, fields=[], message=None, status_code=400):
        self.status_code = status_code
        self.fields = fields
        self.message = message if message else self.message


class PDFNotReadyError(BadRequestError):
    def __init__(self):
        super().__init__(message='PDF not available yet, try again later', status_code=400)


@v3_blueprint.errorhandler(InvalidEmailError)
def invalid_format(error):
    # Note that InvalidEmailError is re-raised for InvalidEmail or InvalidPhone.
    # Work should be done in the utils app to tidy up these errors.
    current_app.logger.info(error)
    return jsonify(status_code=400,
                   errors=[{"error": error.__class__.__name__, "message": str(error)}]), 400

@v3_blueprint.errorhandler(InvalidRequest)
def invalid_data(error):
    current_app.logger.info(error)
    return jsonify(error.to_dict_v2()), error.status_code

@v3_blueprint.errorhandler(UnsupportedMimeTypeException)
def unsupported_mime_type(error):
    current_app.logger.info(error)
    return jsonify(status_code=400,
                   errors=[{"error": error.__class__.__name__, "message": str(error)}]), 400

@v3_blueprint.errorhandler(JobIncompleteError)
def job_incomplete_error(error):
    return jsonify(error.to_dict_v2()), 500

@v3_blueprint.errorhandler(NoResultFound)
@v3_blueprint.errorhandler(DataError)
def no_result_found(e):
    current_app.logger.info(e)
    return jsonify(status_code=404,
                   errors=[{"error": e.__class__.__name__, "message": "No result found"}]), 404

@v3_blueprint.errorhandler(NotImplementedError)
def not_implemented(e):
    current_app.logger.warning(e)
    return jsonify(
        status_code=501,
        errors=[{"error": e.__class__.__name__, "message": "Not implemented"}]
    ), 501

@v3_blueprint.errorhandler(413)
def request_entity_too_large(_e):
    return jsonify(
        status_code=413,
        errors=[{"error": "Request entity too large", "message": "Uploaded attachment exceeds file size limit"}]
    ), 413
