"""
Google Analytics 4
"""

import os

from flask import current_app, Blueprint, send_file
from jsonschema import FormatChecker, ValidationError
from jsonschema.validators import Draft202012Validator

from app.googleanalytics.ga4_schemas import ga4_request_schema
from app.celery.process_ga4_measurement_tasks import post_to_ga4

ga4_blueprint = Blueprint('ga4', __name__, url_prefix='/ga4')

ga4_request_validator = Draft202012Validator(ga4_request_schema, format_checker=FormatChecker(['uuid']))

GA4_PIXEL_TRACKING_IMAGE_PATH = f'{os.getcwd()}/images/ga4_pixel_tracking.png'


@ga4_blueprint.route('/open-email-tracking/<notification>', methods=['GET'])
def get_ga4(notification):
    """
    This route is used for pixel tracking.  It is exercised when a veteran opens an e-mail.
    The route returns a pixel image to avoid a broken icon image in notification emails.
    """
    current_app.logger.debug('GA4 email_opened for notification: %s', notification)

    post_to_ga4.delay(notification, 'email_opened')

    return send_file(GA4_PIXEL_TRACKING_IMAGE_PATH, mimetype='image/png')


@ga4_blueprint.errorhandler(ValidationError)
def ga4_schema_validation_error(error):
    current_app.logger.exception('GA4 ValidationError: %s', error.message)

    return {
        'errors': [
            {
                'error': 'ValidationError',
                'message': error.message,
            }
        ]
    }, 400
