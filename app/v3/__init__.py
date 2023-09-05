from app.authentication.auth import AuthError
from flask import Blueprint
from jsonschema import ValidationError
from werkzeug.exceptions import BadRequest

v3_blueprint = Blueprint("v3", __name__, url_prefix='/v3')


########################################
# Error handlers common to all v3 routes
########################################

@v3_blueprint.errorhandler(AuthError)
def auth_error(error):
    """
    Generally 401 and 403 errors.
    """

    return error.to_dict_v3(), error.code


@v3_blueprint.errorhandler(BadRequest)
def bad_request(error):
    """
    This is for 400 responses not caused by schema validation failure.  If error.__cause__
    is not None, the syntax "raise BadRequest from e" raised the exception.
    """

    return {
        "errors": [
            {
                "error": "BadRequest",
                "message": str(error.__cause__) if (error.__cause__ is not None) else str(error),
            }
        ]
    }, 400


@v3_blueprint.errorhandler(ValidationError)
def bad_request(error):
    """
    This is for schema validation errors, which should result in a 400 response.
    """

    return {
        "errors": [
            {
                "error": "ValidationError",
                "message": error.message,
            }
        ]
    }, 400
