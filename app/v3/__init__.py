"""
Declare all error handlers for v3 in this file.  This ensures consistent error handling
across all v3 endpoints.
"""

from app.authentication.auth import AuthError
from flask import Blueprint, current_app, request
from jsonschema import ValidationError

v3_blueprint = Blueprint("v3", __name__, url_prefix='/v3')


########################################
# Error handlers common to all v3 routes
########################################

@v3_blueprint.errorhandler(AuthError)
def auth_error(error):
    print("MADE IT HERE 2")  # TODO
    current_app.logger.info("API AuthError, client: %s error: %s", request.headers.get("User-Agent"), error)
    # TODO 1360 - standardize this
    return error.to_dict_v2(), error.code


@v3_blueprint.errorhandler(ValidationError)
def validation_error(error):
    return {
        "errors": [
            {
                "error": "ValidationError",
                "message": error.message,
            }
        ]
    }, 400
