"""
Google Analytics 4
"""

import os
from app.googleanalytics.ga4_schemas import ga4_request_schema
from flask import current_app, Blueprint, request
from jsonschema import FormatChecker, ValidationError
from jsonschema.validators import Draft202012Validator

from flask import send_file

ga4_blueprint = Blueprint('ga4', __name__, url_prefix='/ga4')

ga4_request_validator = Draft202012Validator(ga4_request_schema, format_checker=FormatChecker(['uuid']))

if os.environ.get('GITHUB_WORKFLOW') == 1:
    GA4_PIXEL_TRACKING_IMAGE_PATH = 'images/ga4_pixel_tracking.png'
else:
    GA4_PIXEL_TRACKING_IMAGE_PATH = '/app/images/ga4_pixel_tracking.png'


@ga4_blueprint.route('/open-email-tracking', methods=['GET'])
def get_ga4():
    """
    This route is used for pixel tracking.  It is exercised when a veteran opens an e-mail.
    The route returns a pixel image to avoid a broken icon image in notification emails.
    """

    # https://flask.palletsprojects.com/en/3.0.x/api/#flask.Request.args
    url_parameters_dict = request.args.to_dict()

    # This could raise ValidationError.
    ga4_request_validator.validate(url_parameters_dict)

    current_app.logger.info(request.query_string)

    return send_file(GA4_PIXEL_TRACKING_IMAGE_PATH, mimetype='image/png')


@ga4_blueprint.errorhandler(ValidationError)
def ga4_schema_validation_error(error):
    current_app.logger.error('GA4 ValidationError: %s', error.message)

    return {
        'errors': [
            {
                'error': 'ValidationError',
                'message': error.message,
            }
        ]
    }, 400