import base64
import binascii

from sqlalchemy.orm.exc import NoResultFound
from flask import current_app
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.recipients import (
    validate_and_format_phone_number,
    validate_and_format_email_address,
    get_international_phone_info
)
from notifications_utils.clients.redis import rate_limit_cache_key, daily_limit_cache_key

from app.dao import services_dao, templates_dao
from app.dao.service_sms_sender_dao import dao_get_service_sms_sender_by_id
from app.dao.templates_dao import dao_get_number_of_templates_by_service_id_and_name
from app.feature_flags import is_feature_enabled, FeatureFlag
from app.models import (
    INTERNATIONAL_SMS_TYPE, SMS_TYPE, EMAIL_TYPE, LETTER_TYPE,
    KEY_TYPE_TEST, KEY_TYPE_TEAM, SCHEDULE_NOTIFICATIONS
)
from app.service.utils import service_allowed_to_send_to
from app.v2.errors import TooManyRequestsError, BadRequestError, RateLimitError
from app import redis_store
from app.notifications.process_notifications import create_content_for_notification
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_letter_contact_dao import dao_get_letter_contact_by_id


def check_service_over_api_rate_limit(service, api_key):
    if current_app.config['API_RATE_LIMIT_ENABLED'] and current_app.config['REDIS_ENABLED']:
        cache_key = rate_limit_cache_key(service.id, api_key.key_type)
        rate_limit = service.rate_limit
        interval = 60
        if redis_store.exceeded_rate_limit(cache_key, rate_limit, interval):
            current_app.logger.info(f"service {service.id} has been rate limited for throughput")
            raise RateLimitError(rate_limit, interval, key_type=api_key.key_type)


def check_service_over_daily_message_limit(key_type, service):
    if current_app.config['API_MESSAGE_LIMIT_ENABLED'] \
            and key_type != KEY_TYPE_TEST \
            and current_app.config['REDIS_ENABLED']:
        cache_key = daily_limit_cache_key(service.id)
        service_stats = redis_store.get(cache_key)
        if not service_stats:
            service_stats = services_dao.fetch_todays_total_message_count(service.id)
            redis_store.set(cache_key, service_stats, ex=3600)
        if (round((int(service_stats) / service.message_limit), 1) * 100 > 75):
            current_app.logger.info(f'service {service.id} nearing daily limit '
                                    f'{(int(service_stats) / service.message_limit * 100):.1f}%')

        if int(service_stats) >= service.message_limit:
            current_app.logger.info(
                f"service {service.id} has been rate limited for daily use sent"
                f"{int(service_stats)} limit {service.message_limit}"
            )
            raise TooManyRequestsError(service.message_limit)


def check_sms_sender_over_rate_limit(service_id, sms_sender_id):
    if (
        not is_feature_enabled(FeatureFlag.SMS_SENDER_RATE_LIMIT_ENABLED)
        or sms_sender_id is None
    ):
        current_app.logger.info('Skipping sms sender rate limit check')
        return

    sms_sender = dao_get_service_sms_sender_by_id(service_id, sms_sender_id)
    if current_app.config['REDIS_ENABLED']:
        current_app.logger.info('Checking sms sender rate limit')
        cache_key = sms_sender.sms_sender
        rate_limit = sms_sender.rate_limit
        interval = sms_sender.rate_limit_interval
        if redis_store.should_throttle(cache_key, rate_limit, interval):
            current_app.logger.info(f"sms sender {sms_sender.id} has been rate limited for throughput")
            raise RateLimitError(rate_limit, interval)


def check_rate_limiting(service, api_key):
    check_service_over_api_rate_limit(service, api_key)
    check_service_over_daily_message_limit(api_key.key_type, service)


def check_template_is_for_notification_type(notification_type, template_type):
    if notification_type != template_type:
        message = "{0} template is not suitable for {1} notification".format(template_type,
                                                                             notification_type)
        raise BadRequestError(fields=[{'template': message}], message=message)


def check_template_is_active(template):
    if template.archived:
        raise BadRequestError(fields=[{'template': 'Template has been deleted'}],
                              message="Template has been deleted")


def service_can_send_to_recipient(send_to, key_type, service, allow_whitelisted_recipients=True):
    if not service_allowed_to_send_to(send_to, service, key_type, allow_whitelisted_recipients):
        if key_type == KEY_TYPE_TEAM:
            message = 'Can’t send to this recipient using a team-only API key'
        else:
            message = (
                'Can’t send to this recipient when service is in trial mode '
                '– see https://www.notifications.service.gov.uk/trial-mode'
            )
        raise BadRequestError(message=message)


# TODO clean up and remove
def service_has_permission(notify_type, permissions):
    return notify_type in [p.permission for p in permissions]


# TODO clean up and remove
def check_service_can_schedule_notification(permissions, scheduled_for):
    if scheduled_for:
        if not service_has_permission(SCHEDULE_NOTIFICATIONS, permissions):
            raise BadRequestError(message="Cannot schedule notifications (this feature is invite-only)")


def validate_and_format_recipient(send_to, key_type, service, notification_type, allow_whitelisted_recipients=True):
    if send_to is None:
        raise BadRequestError(message="Recipient can't be empty")

    service_can_send_to_recipient(send_to, key_type, service, allow_whitelisted_recipients)

    if notification_type == SMS_TYPE:
        phone_info = get_international_phone_info(send_to)

        if phone_info.international and not service.has_permissions(INTERNATIONAL_SMS_TYPE):
            raise BadRequestError(message="Cannot send to international mobile numbers")

        return validate_and_format_phone_number(
            number=send_to,
            international=phone_info.international
        )
    elif notification_type == EMAIL_TYPE:
        return validate_and_format_email_address(email_address=send_to)


def validate_template(template_id, personalisation, service, notification_type):
    try:
        template = templates_dao.dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service.id
        )
    except NoResultFound:
        message = 'Template not found'
        raise BadRequestError(message=message,
                              fields=[{'template': message}])

    check_template_is_for_notification_type(notification_type, template.template_type)
    check_template_is_active(template)
    template_with_content = create_content_for_notification(template, personalisation)
    if template.template_type == SMS_TYPE and template_with_content.content_count > SMS_CHAR_COUNT_LIMIT:
        current_app.logger.warning("The personalized message length is %s, which exceeds the 4 segments length of %s.",
                                   template_with_content.content_count, SMS_CHAR_COUNT_LIMIT)
    return template, template_with_content


def check_reply_to(service_id, reply_to_id, type_):
    if type_ == EMAIL_TYPE:
        return check_service_email_reply_to_id(service_id, reply_to_id, type_)
    elif type_ == SMS_TYPE:
        return check_service_sms_sender_id(service_id, reply_to_id, type_)
    elif type_ == LETTER_TYPE:
        return check_service_letter_contact_id(service_id, reply_to_id, type_)


def check_service_email_reply_to_id(service_id, reply_to_id, notification_type):
    if reply_to_id:
        try:
            return dao_get_reply_to_by_id(service_id, reply_to_id).email_address
        except NoResultFound:
            message = 'email_reply_to_id {} does not exist in database for service id {}'\
                .format(reply_to_id, service_id)
            raise BadRequestError(message=message)


def check_service_sms_sender_id(service_id, sms_sender_id, notification_type):
    if sms_sender_id is not None:
        try:
            return dao_get_service_sms_sender_by_id(service_id, sms_sender_id).sms_sender
        except NoResultFound:
            message = f'sms_sender_id {sms_sender_id} does not exist in database for service id {service_id}'
            raise BadRequestError(message=message)


def check_service_letter_contact_id(service_id, letter_contact_id, notification_type):
    if letter_contact_id:
        try:
            return dao_get_letter_contact_by_id(service_id, letter_contact_id).contact_block
        except NoResultFound:
            message = 'letter_contact_id {} does not exist in database for service id {}'\
                .format(letter_contact_id, service_id)
            raise BadRequestError(message=message)


def decode_personalisation_files(personalisation_data):
    errors = []
    file_keys = [k for k, v in personalisation_data.items() if isinstance(v, dict) and 'file' in v]
    for key in file_keys:
        try:
            personalisation_data[key]['file'] = base64.b64decode(personalisation_data[key]['file'])
        except binascii.Error as e:
            errors.append({
                "error": "ValidationError",
                "message": f"{key} : {str(e)} : Error decoding base64 field"
            })
    return personalisation_data, errors


def template_name_already_exists_on_service(service_id, template_name):
    return dao_get_number_of_templates_by_service_id_and_name(service_id, template_name) > 0
