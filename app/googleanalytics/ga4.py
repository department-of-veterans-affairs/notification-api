"""
Google Analytics 4
"""

import os

from flask import current_app, Blueprint, send_file

from app.celery.process_ga4_measurement_tasks import post_to_ga4

ga4_blueprint = Blueprint('ga4', __name__, url_prefix='/ga4')

GA4_PIXEL_TRACKING_IMAGE_PATH = f'{os.getcwd()}/images/ga4_pixel_tracking.png'


@ga4_blueprint.route('/open-email-tracking/<notification>', methods=['GET'])
def get_ga4(notification):
    """
    This route is used for pixel tracking.  It is exercised when a veteran opens an e-mail.
    The route returns a pixel image to avoid a broken icon image in notification emails.
    """
    current_app.logger.debug('GA4 email_opened for notification: %s', notification)

    post_to_ga4.delay(
        notification,
        current_app.config['GA4_PIXEL_TRACKING_NAME'],
        current_app.config['GA4_PIXEL_TRACKING_SOURCE'],
        current_app.config['GA4_PIXEL_TRACKING_MEDIUM'],
    )

    return send_file(GA4_PIXEL_TRACKING_IMAGE_PATH, mimetype='image/png')
