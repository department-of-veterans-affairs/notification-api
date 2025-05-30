import os
import random
import string

from dotenv import load_dotenv
from flask import request, g, jsonify, make_response
from flask_marshmallow import Marshmallow
from flask_migrate import Migrate
from time import monotonic
from notifications_utils.clients.zendesk.zendesk_client import ZendeskClient
from notifications_utils.clients.statsd.statsd_client import StatsdClient
from notifications_utils.clients.redis.redis_client import RedisClient
from notifications_utils import logging, request_helper
from werkzeug.exceptions import (
    HTTPException as WerkzeugHTTPException,
    RequestEntityTooLarge,
)
from werkzeug.local import LocalProxy

from app.callback.sqs_client import SQSClient
from app.celery.celery import NotifyCelery
from app.clients import Clients
from app.clients.email.aws_ses import AwsSesClient
from app.clients.sms.firetext import FiretextClient
from app.clients.sms.loadtesting import LoadtestingClient
from app.clients.sms.mmg import MMGClient
from app.clients.sms.aws_sns import AwsSnsClient
from app.clients.sms.twilio import TwilioSMSClient
from app.clients.sms.aws_pinpoint import AwsPinpointClient
from app.clients.performance_platform.performance_platform_client import PerformancePlatformClient
from app.feature_flags import FeatureFlag, is_feature_enabled
from app.va.va_profile import VAProfileClient
from app.va.mpi import MpiClient
from app.va.vetext import VETextClient
from app.encryption import Encryption
from app.attachments.store import AttachmentStore
from app.db import db
from app.mobile_app.mobile_app_registry import MobileAppRegistry

load_dotenv()


migrate = Migrate()
ma = Marshmallow()
notify_celery = NotifyCelery()
encryption = Encryption()
firetext_client = FiretextClient()
loadtest_client = LoadtestingClient()
mmg_client = MMGClient()
aws_ses_client = AwsSesClient()

# This is initialized below, in create_app.
mobile_app_registry = None

from app.clients.email.govdelivery_client import GovdeliveryClient  # noqa

govdelivery_client = GovdeliveryClient()
aws_sns_client = AwsSnsClient()
twilio_sms_client = TwilioSMSClient(
    account_sid=os.getenv('TWILIO_ACCOUNT_SID'),
    auth_token=os.getenv('TWILIO_AUTH_TOKEN'),
)
aws_pinpoint_client = AwsPinpointClient()
sqs_client = SQSClient()
zendesk_client = ZendeskClient()
statsd_client = StatsdClient()
redis_store = RedisClient()
performance_platform_client = PerformancePlatformClient()
va_profile_client = VAProfileClient()
mpi_client = MpiClient()
vetext_client = VETextClient()

attachment_store = AttachmentStore()

clients = Clients()

from app.oauth.jwt_manager import jwt  # noqa

from app.provider_details.provider_service import ProviderService  # noqa

# This isn't used in this file, but it's imported elsewhere.
provider_service = ProviderService()

api_user = LocalProxy(lambda: g.api_user)
authenticated_service = LocalProxy(lambda: g.authenticated_service)


def create_app(application):
    """
    https://flask.palletsprojects.com/en/2.3.x/tutorial/factory/
    """

    from app.config import configs

    notify_environment = os.getenv('NOTIFY_ENVIRONMENT', 'development')

    application.config.from_object(configs[notify_environment])
    if notify_environment == 'test':
        # Set the read-db to be the same as the write/default instance.
        application.config['SQLALCHEMY_BINDS'] = {'read-db': application.config['SQLALCHEMY_DATABASE_URI']}
        assert application.config['SQLALCHEMY_DATABASE_URI'].endswith('notification_api'), (
            "Don't run tests against the main writer database."
        )
        assert application.config['SQLALCHEMY_BINDS']['read-db'].endswith('notification_api'), (
            "Don't run tests against the main reader database."
        )

    application.config['NOTIFY_APP_NAME'] = application.name
    init_app(application)
    request_helper.init_app(application)

    # https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/api/#flask_sqlalchemy.SQLAlchemy.init_app
    db.init_app(application)

    migrate.init_app(application, db=db)
    ma.init_app(application)
    zendesk_client.init_app(application)
    statsd_client.init_app(application)
    logging.init_app(application, statsd_client)
    firetext_client.init_app(application, statsd_client=statsd_client)
    loadtest_client.init_app(application, statsd_client=statsd_client)
    mmg_client.init_app(application, statsd_client=statsd_client)
    aws_sns_client.init_app(
        aws_region=application.config['AWS_REGION'],
        statsd_client=statsd_client,
        logger=application.logger,
    )
    aws_ses_client.init_app(
        application.config['AWS_REGION'],
        logger=application.logger,
        statsd_client=statsd_client,
        email_from_domain=application.config['AWS_SES_EMAIL_FROM_DOMAIN'],
        email_from_user=application.config['AWS_SES_EMAIL_FROM_USER'],
        default_reply_to=application.config['AWS_SES_DEFAULT_REPLY_TO'],
        configuration_set=application.config['AWS_SES_CONFIGURATION_SET'],
        endpoint_url=application.config['AWS_SES_ENDPOINT_URL'],
    )
    govdelivery_client.init_app(
        application.config['GRANICUS_TOKEN'],
        application.config['GRANICUS_URL'],
        statsd_client,
    )
    twilio_sms_client.init_app(
        logger=application.logger,
        callback_notify_url_host=application.config['API_HOST_NAME'],
        environment=notify_environment,
    )
    aws_pinpoint_client.init_app(
        application.config['AWS_PINPOINT_APP_ID'],
        application.config['AWS_REGION'],
        application.logger,
        application.config['FROM_NUMBER'],
        statsd_client,
    )
    sqs_client.init_app(application.config['AWS_REGION'], application.logger, statsd_client)
    va_profile_client.init_app(
        application.logger,
        application.config['VA_PROFILE_URL'],
        application.config['VANOTIFY_SSL_CERT_PATH'],
        application.config['VANOTIFY_SSL_KEY_PATH'],
        application.config['VA_PROFILE_TOKEN'],
        statsd_client,
    )
    mpi_client.init_app(
        application.logger,
        application.config['MPI_URL'],
        application.config['VANOTIFY_SSL_CERT_PATH'],
        application.config['VANOTIFY_SSL_KEY_PATH'],
        statsd_client,
    )
    vetext_client.init_app(
        application.config['VETEXT_URL'],
        {
            'username': application.config['VETEXT_USERNAME'],
            'password': application.config['VETEXT_PASSWORD'],
        },
        application.logger,
        statsd_client,
    )

    notify_celery.init_app(application)
    encryption.init_app(application)
    redis_store.init_app(application)
    performance_platform_client.init_app(application)
    clients.init_app(
        sms_clients=[
            firetext_client,
            mmg_client,
            aws_sns_client,
            loadtest_client,
            twilio_sms_client,
            aws_pinpoint_client,
        ],
        email_clients=[aws_ses_client, govdelivery_client],
    )

    attachment_store.init_app(
        endpoint_url=application.config['AWS_S3_ENDPOINT_URL'],
        bucket=application.config['ATTACHMENTS_BUCKET'],
        logger=application.logger,
        statsd_client=statsd_client,
    )

    jwt.init_app(application)

    global mobile_app_registry
    mobile_app_registry = MobileAppRegistry(application.logger)

    register_blueprint(application)
    register_v2_blueprints(application)

    if is_feature_enabled(FeatureFlag.V3_ENABLED):
        register_v3_blueprints(application)

    # avoid circular imports by importing this file later
    from app.commands import setup_commands

    setup_commands(application)

    return application


def register_blueprint(application):
    from app.googleanalytics.ga4 import ga4_blueprint
    from app.internal.rest import internal_blueprint
    from app.service.rest import service_blueprint
    from app.service.callback_rest import service_callback_blueprint
    from app.service.sms_sender_rest import service_sms_sender_blueprint
    from app.user.rest import user_blueprint
    from app.template.rest import template_blueprint
    from app.status.healthcheck import status as status_blueprint
    from app.template_statistics.rest import (
        template_statistics as template_statistics_blueprint,
    )
    from app.provider_details.rest import provider_details as provider_details_blueprint
    from app.inbound_number.rest import inbound_number_blueprint
    from app.inbound_sms.rest import inbound_sms as inbound_sms_blueprint
    from app.authentication.auth import (
        validate_admin_auth,
        do_not_validate_auth,
    )
    from app.billing.rest import billing_blueprint
    from app.platform_stats.rest import platform_stats_blueprint
    from app.communication_item.rest import communication_item_blueprint

    application.register_blueprint(ga4_blueprint)
    application.register_blueprint(internal_blueprint)

    application.register_blueprint(service_blueprint, url_prefix='/service')

    user_blueprint.before_request(validate_admin_auth)
    application.register_blueprint(user_blueprint, url_prefix='/user')

    application.register_blueprint(template_blueprint)

    status_blueprint.before_request(do_not_validate_auth)
    application.register_blueprint(status_blueprint)

    inbound_number_blueprint.before_request(validate_admin_auth)
    application.register_blueprint(inbound_number_blueprint)

    inbound_sms_blueprint.before_request(validate_admin_auth)
    application.register_blueprint(inbound_sms_blueprint)

    template_statistics_blueprint.before_request(validate_admin_auth)
    application.register_blueprint(template_statistics_blueprint)

    provider_details_blueprint.before_request(validate_admin_auth)
    application.register_blueprint(provider_details_blueprint, url_prefix='/provider-details')

    billing_blueprint.before_request(validate_admin_auth)
    application.register_blueprint(billing_blueprint)

    application.register_blueprint(service_callback_blueprint)
    application.register_blueprint(service_sms_sender_blueprint)

    application.register_blueprint(platform_stats_blueprint, url_prefix='/platform-stats')

    communication_item_blueprint.before_request(validate_admin_auth)
    application.register_blueprint(communication_item_blueprint)


def register_v2_blueprints(application):
    from app.v2.notifications.post_notifications import v2_notification_blueprint as v2_notifications  # Get is the same
    from app.v2.notifications.get_notifications import v2_notification_blueprint as get_notifications
    from app.v2.templates.get_templates import v2_templates_blueprint as get_templates
    from app.v2.template.post_template import v2_template_blueprint as post_template  # Get is the same
    from app.v2.template.get_template import v2_template_blueprint as get_template
    from app.authentication.auth import validate_service_api_key_auth

    v2_notifications.before_request(validate_service_api_key_auth)
    get_notifications.before_request(validate_service_api_key_auth)
    application.register_blueprint(v2_notifications)

    get_templates.before_request(validate_service_api_key_auth)
    application.register_blueprint(get_templates)

    post_template.before_request(validate_service_api_key_auth)
    get_template.before_request(validate_service_api_key_auth)
    application.register_blueprint(post_template)


def register_v3_blueprints(application):
    """
    Only the top level v3_blueprint should be registered directly with the application.  Register all
    child blueprints with v3_blueprint.  This helps to standardize error handling across all v3 routes.
    See app/v3/__init__.py.
    """

    from app.authentication.auth import validate_service_api_key_auth
    from app.v3 import v3_blueprint

    # Notifications
    from app.v3.notifications.rest import v3_notifications_blueprint

    v3_notifications_blueprint.before_request(validate_service_api_key_auth)
    v3_blueprint.register_blueprint(v3_notifications_blueprint)

    application.register_blueprint(v3_blueprint)


def init_app(app):
    @app.before_request
    def record_user_agent():
        statsd_client.incr('user-agent.{}'.format(process_user_agent(request.headers.get('User-Agent', None))))

    @app.before_request
    def reject_payload_over_max_content_length():
        if (
            request.headers.get('Content-Length')
            and app.config.get('MAX_CONTENT_LENGTH')
            and int(request.headers['Content-Length']) > app.config['MAX_CONTENT_LENGTH']
        ):
            raise RequestEntityTooLarge()

    @app.before_request
    def record_request_details():
        g.start = monotonic()
        g.endpoint = request.endpoint

    @app.errorhandler(WerkzeugHTTPException)
    def werkzeug_exception(e):
        return make_response(jsonify(result='error', message=e.description), e.code, e.get_headers())

    @app.errorhandler(404)
    def page_not_found(e):
        msg = e.description or 'Not found'
        return jsonify(result='error', message=msg), 404

    @app.errorhandler(409)
    def handle_conflict(error):
        return jsonify(message=str(error.description)), 409

    @app.errorhandler(Exception)
    def exception(error):
        app.logger.exception(error)
        return jsonify(result='error', message='Internal server error'), 500


def create_random_identifier():
    # the random.choice is used for letter reference number; is not used in security context
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))  # nosec


def process_user_agent(user_agent_string):
    if user_agent_string and user_agent_string.lower().startswith('notify'):
        components = user_agent_string.split('/')
        client_name = components[0].lower()
        client_version = components[1].replace('.', '-')
        return '{}.{}'.format(client_name, client_version)
    elif user_agent_string and not user_agent_string.lower().startswith('notify'):
        return 'non-notify-user-agent'
    else:
        return 'unknown'
