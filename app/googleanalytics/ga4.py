"""
Google Analytics 4
"""

from app.googleanalytics.ga4_schemas import ga4_request_schema
from flask import current_app, Blueprint, request
from jsonschema import FormatChecker, ValidationError
from jsonschema.validators import Draft202012Validator

from app.celery.process_ga4_measurement_tasks import post_to_ga4


ga4_blueprint = Blueprint('ga4', __name__, url_prefix='/ga4')

ga4_request_validator = Draft202012Validator(ga4_request_schema, format_checker=FormatChecker(['uuid']))


@ga4_blueprint.route('/open-email-tracking', methods=['GET'])
def get_ga4():
    """
    This route is used for pixel tracking.  It is exercised when a veteran opens an e-mail.
    """

    # https://flask.palletsprojects.com/en/3.0.x/api/#flask.Request.args
    url_parameters_dict = request.args.to_dict()

    # This could raise ValidationError.
    ga4_request_validator.validate(url_parameters_dict)

    current_app.logger.debug(request.query_string)

    template_name = url_parameters_dict['campaign']
    template_id = url_parameters_dict['campaign_id']
    name = url_parameters_dict['name']
    source = url_parameters_dict['source']
    medium = url_parameters_dict['medium']

    content = url_parameters_dict['content'].split('/')
    service_name = content[0]
    service_id = content[1]
    notification_id = content[2]

    current_app.logger.info(
        f'GA4: campaign={template_name}, campaign_id={template_id}, name={name}, source={source}, medium={medium}, content={content}'
    )
    post_to_ga4.delay(
        notification_id=notification_id,
        template_name=template_name,
        template_id=template_id,
        service_id=service_id,
        service_name=service_name,
    )
    # "No Content"
    return {}, 204


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
