import itertools
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from flask import current_app, Blueprint, jsonify, request
from flask.wrappers import Response
from nanoid import generate
from notifications_utils.letter_timings import letter_can_be_cancelled
from notifications_utils.timezones import convert_utc_to_local_timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.authentication.auth import requires_admin_auth, requires_admin_auth_or_user_in_service
from app.constants import LETTER_TYPE, NOTIFICATION_CANCELLED
from app.dao import fact_notification_status_dao, notifications_dao
from app.dao.api_key_dao import (
    get_model_api_key,
    save_model_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    expire_api_key,
)
from app.dao.date_util import get_financial_year
from app.dao.fact_notification_status_dao import (
    fetch_notification_status_for_service_by_month,
    fetch_notification_status_for_service_for_day,
    fetch_notification_status_for_service_for_today_and_7_previous_days,
    fetch_stats_for_all_services_by_date_range,
    fetch_monthly_template_usage_for_service,
)
from app.dao.organisation_dao import dao_get_organisation_by_service_id
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_create_service,
    dao_archive_service,
    dao_fetch_all_services,
    dao_fetch_all_services_by_user,
    dao_fetch_live_services_data,
    dao_fetch_service_by_id,
    dao_fetch_todays_stats_for_service,
    dao_fetch_todays_stats_for_all_services,
    dao_resume_service,
    dao_remove_user_from_service,
    dao_suspend_service,
    dao_update_service,
    get_services_by_partial_name,
)
from app.dao.service_data_retention_dao import (
    fetch_service_data_retention,
    fetch_service_data_retention_by_id,
    fetch_service_data_retention_by_notification_type,
    insert_service_data_retention,
    update_service_data_retention,
)
from app.dao.users_dao import get_user_by_id
from app.errors import InvalidRequest, register_errors
from app.letters.utils import letter_print_day
from app.models import (
    Permission,
    Service,
    EmailBranding,
)
from app.schema_validation import validate
from app.service import statistics
from app.service.send_notification import send_one_off_notification
from app.service.sender import send_notification_to_service_users
from app.service.service_data_retention_schema import (
    add_service_data_retention_request,
    update_service_data_retention_request,
)
from app.schemas import (
    service_schema,
    api_key_schema,
    notification_with_template_schema,
    notifications_filter_schema,
    detailed_service_schema,
)
from app.smtp.aws import smtp_add, smtp_get_user_key, smtp_remove
from app.user.users_schema import post_set_permissions_schema
from app.utils import pagination_links

CAN_T_BE_EMPTY_ERROR_MESSAGE = "Can't be empty"

service_blueprint = Blueprint('service', __name__)

register_errors(service_blueprint)


@service_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint on ix_organisation_name
    """

    if any(
        'duplicate key value violates unique constraint "{}"'.format(constraint) in str(exc)
        for constraint in {'services_name_key', 'services_email_from_key'}
    ):
        return jsonify(
            result='error',
            message={
                'name': ["Duplicate service name '{}'".format(exc.params.get('name', exc.params.get('email_from', '')))]
            },
        ), 400
    current_app.logger.exception(exc)
    return jsonify(result='error', message='Internal server error'), 500


@service_blueprint.route('', methods=['GET'])
@requires_admin_auth()
def get_services():
    only_active = request.args.get('only_active') == 'True'
    detailed = request.args.get('detailed') == 'True'
    user_id = request.args.get('user_id', None)
    include_from_test_key = request.args.get('include_from_test_key', 'True') != 'False'

    # If start and end date are not set, we are expecting today's stats.
    today = str(datetime.utcnow().date())

    start_date = datetime.strptime(request.args.get('start_date', today), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.args.get('end_date', today), '%Y-%m-%d').date()

    if user_id:
        services = dao_fetch_all_services_by_user(user_id, only_active)
    elif detailed:
        result = jsonify(
            data=get_detailed_services(
                start_date=start_date,
                end_date=end_date,
                only_active=only_active,
                include_from_test_key=include_from_test_key,
            )
        )
        return result
    else:
        services = dao_fetch_all_services(only_active)
    data = service_schema.dump(services, many=True)
    return jsonify(data=data)


@service_blueprint.route('/find-services-by-name', methods=['GET'])
@requires_admin_auth()
def find_services_by_name():
    service_name = request.args.get('service_name')
    if not service_name:
        errors = {'service_name': ['Missing data for required field.']}
        raise InvalidRequest(errors, status_code=400)
    fetched_services = get_services_by_partial_name(service_name)
    data = [service.serialize_for_org_dashboard() for service in fetched_services]
    return jsonify(data=data), 200


@service_blueprint.route('/live-services-data', methods=['GET'])
@requires_admin_auth()
def get_live_services_data():
    data = dao_fetch_live_services_data()
    return jsonify(data=data)


@service_blueprint.route('/<uuid:service_id>', methods=['GET'])
@requires_admin_auth_or_user_in_service()
def get_service_by_id(service_id):
    if request.args.get('detailed') == 'True':
        data = get_detailed_service(service_id, today_only=request.args.get('today_only') == 'True')
    else:
        fetched = dao_fetch_service_by_id(service_id)

        data = service_schema.dump(fetched)
    return jsonify(data=data)


@service_blueprint.route('/<uuid:service_id>/statistics')
@requires_admin_auth()
def get_service_notification_statistics(service_id):
    return jsonify(
        data=get_service_statistics(
            service_id, request.args.get('today_only') == 'True', int(request.args.get('limit_days', 7))
        )
    )


@service_blueprint.route('', methods=['POST'])
@requires_admin_auth()
def create_service():
    data = request.get_json()

    if not data.get('user_id'):
        errors = {'user_id': ['Missing data for required field.']}
        raise InvalidRequest(errors, status_code=400)
    data.pop('service_domain', None)
    user = get_user_by_id(data.pop('user_id'))

    # validate json with marshmallow
    service_schema.load(data)

    # unpack valid json into service object
    valid_service = Service.from_json(data)

    dao_create_service(valid_service, user)

    return jsonify(data=service_schema.dump(valid_service)), 201


@service_blueprint.route('/<uuid:service_id>', methods=['POST'])
@requires_admin_auth()
def update_service(service_id):
    req_json = request.get_json()

    fetched_service = dao_fetch_service_by_id(service_id)
    # Capture the status change here as Marshmallow changes this later
    service_going_live = fetched_service.restricted and not req_json.get('restricted', True)
    current_data = service_schema.dump(fetched_service)
    current_data.update(request.get_json())

    service = service_schema.load(current_data)

    if 'email_branding' in req_json:
        email_branding_id = req_json['email_branding']
        service.email_branding = None if not email_branding_id else db.session.get(EmailBranding, email_branding_id)

    dao_update_service(service)

    if service_going_live:
        send_notification_to_service_users(
            service_id=service_id,
            template_id=current_app.config['SERVICE_NOW_LIVE_TEMPLATE_ID'],
            personalisation={
                'service_name': current_data['name'],
                'message_limit': '{:,}'.format(current_data['message_limit']),
            },
            include_user_fields=['name'],
        )

    return jsonify(data=service_schema.dump(fetched_service)), 200


@service_blueprint.route('/<uuid:service_id>/api-key', methods=['POST'])
@requires_admin_auth()
def create_api_key(service_id: UUID) -> tuple[Response, Literal[201, 400]]:
    """Create API key for the given service.

    Args:
        service_id (UUID): The id of the service the api key is being added to.

    Returns:
        tuple[Response, Literal[201, 400]]:
        - The response includes the unencrypted key and a 201 response if successful.

    Raises:
        InvalidRequest: 400 Bad Request
        - If unsuccessful for a variety of reasons a usefull error message is provided in the json response body.
    """
    err_msg = 'Could not create requested API key.'

    fetched_service = dao_fetch_service_by_id(service_id=service_id)

    try:
        valid_api_key = api_key_schema.load(request.get_json())
    except DataError:
        err_msg += ' DataError, ensure created_by user id is a valid uuid'
        current_app.logger.exception(err_msg)
        raise InvalidRequest(err_msg, 400)

    valid_api_key.service = fetched_service
    valid_api_key.expiry_date = datetime.utcnow() + timedelta(days=180)

    try:
        save_model_api_key(valid_api_key)
    except IntegrityError:
        err_msg += ' DB IntegrityError, ensure created_by id is valid and key_type is one of [normal, team, test]'
        current_app.logger.exception(err_msg)
        raise InvalidRequest(err_msg, 400)

    unsigned_api_key = get_unsigned_secret(valid_api_key.id)

    return jsonify(data=unsigned_api_key), 201


@service_blueprint.route('/<uuid:service_id>/api-key/revoke/<uuid:api_key_id>', methods=['POST'])
@requires_admin_auth()
def revoke_api_key(
    service_id: UUID,
    api_key_id: UUID,
) -> tuple[Response, Literal[202, 404]]:
    """Revokes the API key for the given service and key id.

    Args:
        service_id (UUID): The id of the service to which the soon to be revoked key belongs
        api_key_id (UUID): The id of the key to revoke

    Returns:
        tuple[Response, Literal[202, 404]]: 202 Accepted
        - If the requested api key was found and revoked.

    Raises:
        InvalidRequest: 404 NoResultsFound
        - If the service or key is not found.
    """
    try:
        expire_api_key(service_id=service_id, api_key_id=api_key_id)
    except NoResultFound:
        error_message = f'No valid API key found for service {service_id} with id {api_key_id}'
        raise InvalidRequest(error_message, status_code=404)
    return jsonify(), 202


@service_blueprint.route('/<uuid:service_id>/api-keys', methods=['GET'])
@service_blueprint.route('/<uuid:service_id>/api-keys/<uuid:key_id>', methods=['GET'])
@requires_admin_auth()
def get_api_keys(
    service_id: UUID,
    key_id: UUID | None = None,
) -> tuple[Response, Literal[200, 404]]:
    """Returns a list of api keys from the given service.

    Args:
        service_id (UUID): The uuid of the service from which to pull keys
        key_id (UUID): The uuid of the key to lookup

    Params:
        include_revoked: Including this param will return all keys, including revoked ones. By default, returns only
        non-revoked keys.

    Returns:
        tuple[Response, Literal[200, 404]]: 200 OK
        - Returns json list of API keys for the given service, or a list with the indicated key if a key_id is included.

    Raises:
        InvalidRequest: 404 NoResultsFound
        - If there are no valid API keys for the requested service, or the requested service id does not exist.
    """
    include_revoked = request.args.get('include_revoked', 'f')
    include_revoked = str(include_revoked).lower()
    if include_revoked not in ('true', 't', 'false', 'f'):
        raise InvalidRequest('Invalid value for include_revoked', status_code=400)
    include_revoked = include_revoked in ('true', 't')

    dao_fetch_service_by_id(service_id=service_id)

    try:
        if key_id:
            api_keys = [get_model_api_key(key_id=key_id)]
        else:
            api_keys = get_model_api_keys(service_id=service_id, include_revoked=include_revoked)
    except NoResultFound:
        error = f'No valid API key found for service {service_id}'
        raise InvalidRequest(error, status_code=404)

    return jsonify(apiKeys=api_key_schema.dump(api_keys, many=True)), 200


@service_blueprint.route('/<uuid:service_id>/users', methods=['GET'])
@requires_admin_auth()
def get_users_for_service(service_id):
    fetched = dao_fetch_service_by_id(service_id)
    return jsonify(data=[x.serialize() for x in fetched.users])


@service_blueprint.route('/<uuid:service_id>/users/<user_id>', methods=['POST'])
@requires_admin_auth()
def add_user_to_service(
    service_id,
    user_id,
):
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)

    if user in service.users:
        error = 'User id: {} already part of service id: {}'.format(user_id, service_id)
        raise InvalidRequest(error, status_code=400)

    data = request.get_json()
    validate(data, post_set_permissions_schema)

    permissions = [
        Permission(service_id=service_id, user_id=user_id, permission=p['permission']) for p in data['permissions']
    ]
    folder_permissions = data.get('folder_permissions', [])

    dao_add_user_to_service(service, user, permissions, folder_permissions)
    data = service_schema.dump(service)
    return jsonify(data=data), 201


@service_blueprint.route('/<uuid:service_id>/users/<user_id>', methods=['DELETE'])
@requires_admin_auth()
def remove_user_from_service(
    service_id,
    user_id,
):
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)
    if user not in service.users:
        error = 'User not found'
        raise InvalidRequest(error, status_code=404)

    elif len(service.users) == 1:
        error = 'You cannot remove the only user for a service'
        raise InvalidRequest(error, status_code=400)

    dao_remove_user_from_service(service, user)
    return jsonify({}), 204


# This is placeholder get method until more thought
# goes into how we want to fetch and view various items in history
# tables. This is so product owner can pass stories as done.
@service_blueprint.route('/<uuid:service_id>/history', methods=['GET'])
@requires_admin_auth()
def get_service_history(service_id):
    from app.models import Service, ApiKey, TemplateHistory
    from app.schemas import service_history_schema, api_key_history_schema, template_history_schema

    service_history_model = Service.get_history_model()
    stmt = select(service_history_model).where(service_history_model.id == service_id)
    service_history = db.session.scalars(stmt).all()

    service_data = service_history_schema.dump(service_history, many=True)

    api_key_history_model = ApiKey.get_history_model()
    stmt = select(api_key_history_model).where(api_key_history_model.service_id == service_id)
    api_key_history = db.session.scalars(stmt).all()

    api_keys_data = api_key_history_schema.dump(api_key_history, many=True)

    stmt = select(TemplateHistory).where(TemplateHistory.service_id == service_id)
    template_history = db.session.scalars(stmt).all()

    template_data = template_history_schema.dump(template_history, many=True)

    data = {
        'service_history': service_data,
        'api_key_history': api_keys_data,
        'template_history': template_data,
        'events': [],
    }

    return jsonify(data=data)


@service_blueprint.route('/<uuid:service_id>/notifications', methods=['GET'])
@requires_admin_auth()
def get_all_notifications_for_service(service_id):
    data = notifications_filter_schema.load(request.args)
    if data.get('to'):
        notification_type = data.get('template_type')[0] if data.get('template_type') else None
        return search_for_notification_by_to_field(
            service_id=service_id,
            search_term=data['to'],
            statuses=data.get('status'),
            notification_type=notification_type,
        )
    page = data['page'] if 'page' in data else 1
    page_size = data['page_size'] if 'page_size' in data else current_app.config.get('PAGE_SIZE')
    limit_days = data.get('limit_days')
    include_jobs = data.get('include_jobs', True)
    include_from_test_key = data.get('include_from_test_key', False)
    include_one_off = data.get('include_one_off', True)

    count_pages = data.get('count_pages', True)

    pagination = notifications_dao.get_notifications_for_service(
        service_id,
        filter_dict=data,
        page=page,
        page_size=page_size,
        count_pages=count_pages,
        limit_days=limit_days,
        include_jobs=include_jobs,
        include_from_test_key=include_from_test_key,
        include_one_off=include_one_off,
    )

    kwargs = request.args.to_dict()
    kwargs['service_id'] = service_id

    if data.get('format_for_csv'):
        notifications = [notification.serialize_for_csv() for notification in pagination.items]
    else:
        notifications = notification_with_template_schema.dump(pagination.items, many=True)
    return jsonify(
        notifications=notifications,
        page_size=page_size,
        total=pagination.total,
        links=pagination_links(pagination, '.get_all_notifications_for_service', **kwargs),
    ), 200


@service_blueprint.route('/<uuid:service_id>/notifications/<uuid:notification_id>', methods=['GET'])
@requires_admin_auth()
def get_notification_for_service(
    service_id,
    notification_id,
):
    notification = notifications_dao.get_notification_with_personalisation(
        service_id,
        notification_id,
        key_type=None,
    )
    return jsonify(
        notification_with_template_schema.dump(notification),
    ), 200


@service_blueprint.route('/<uuid:service_id>/notifications/<uuid:notification_id>/cancel', methods=['POST'])
@requires_admin_auth()
def cancel_notification_for_service(
    service_id,
    notification_id,
):
    notification = notifications_dao.get_notification_by_id(notification_id, service_id)

    if not notification:
        raise InvalidRequest('Notification not found', status_code=404)
    elif notification.notification_type != LETTER_TYPE:
        raise InvalidRequest('Notification cannot be cancelled - only letters can be cancelled', status_code=400)
    elif not letter_can_be_cancelled(notification.status, notification.created_at):
        print_day = letter_print_day(notification.created_at)

        raise InvalidRequest(
            'It’s too late to cancel this letter. Printing started {} at 5.30pm'.format(print_day), status_code=400
        )

    updated_notification = notifications_dao.update_notification_status_by_id(
        notification_id,
        NOTIFICATION_CANCELLED,
    )

    return jsonify(notification_with_template_schema.dump(updated_notification)), 200


def search_for_notification_by_to_field(
    service_id,
    search_term,
    statuses,
    notification_type,
):
    results = notifications_dao.dao_get_notifications_by_to_field(
        service_id=service_id, search_term=search_term, statuses=statuses, notification_type=notification_type
    )
    return jsonify(notifications=notification_with_template_schema.dump(results, many=True)), 200


@service_blueprint.route('/<uuid:service_id>/notifications/monthly', methods=['GET'])
@requires_admin_auth()
def get_monthly_notification_stats(service_id):
    # check service_id validity
    dao_fetch_service_by_id(service_id)

    try:
        year = int(request.args.get('year', 'NaN'))
    except ValueError:
        raise InvalidRequest('Year must be a number', status_code=400)

    start_date, end_date = get_financial_year(year)

    data = statistics.create_empty_monthly_notification_status_stats_dict(year)

    stats = fetch_notification_status_for_service_by_month(start_date, end_date, service_id)
    statistics.add_monthly_notification_status_stats(data, stats)

    now = datetime.utcnow()
    if end_date > now:
        todays_deltas = fetch_notification_status_for_service_for_day(
            convert_utc_to_local_timezone(now), service_id=service_id
        )
        statistics.add_monthly_notification_status_stats(data, todays_deltas)

    return jsonify(data=data)


def get_detailed_service(
    service_id,
    today_only=False,
):
    service = dao_fetch_service_by_id(service_id)

    service.statistics = get_service_statistics(service_id, today_only)
    return detailed_service_schema.dump(service)


def get_service_statistics(
    service_id,
    today_only,
    limit_days=7,
):
    # today_only flag is used by the send page to work out if the service will exceed their daily usage by sending a job
    if today_only:
        stats = dao_fetch_todays_stats_for_service(service_id)
    else:
        stats = fetch_notification_status_for_service_for_today_and_7_previous_days(service_id, limit_days=limit_days)

    return statistics.format_statistics(stats)


def get_detailed_services(
    start_date,
    end_date,
    only_active=False,
    include_from_test_key=True,
):
    if start_date == datetime.utcnow().date():
        stats = dao_fetch_todays_stats_for_all_services(
            include_from_test_key=include_from_test_key, only_active=only_active
        )
    else:
        stats = fetch_stats_for_all_services_by_date_range(
            start_date=start_date,
            end_date=end_date,
            include_from_test_key=include_from_test_key,
        )
    results = []
    for service_id, rows in itertools.groupby(stats, lambda x: x.service_id):
        rows = list(rows)
        s = statistics.format_statistics(rows)
        results.append(
            {
                'id': str(rows[0].service_id),
                'name': rows[0].name,
                'notification_type': rows[0].notification_type,
                'research_mode': rows[0].research_mode,
                'restricted': rows[0].restricted,
                'active': rows[0].active,
                'created_at': rows[0].created_at,
                'statistics': s,
            }
        )
    return results


@service_blueprint.route('/<uuid:service_id>/archive', methods=['POST'])
@requires_admin_auth()
def archive_service(service_id):
    """
    When a service is archived the service is made inactive, templates are archived and api keys are revoked.
    There is no coming back from this operation.
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if service.active:
        dao_archive_service(service.id)

    return '', 204


@service_blueprint.route('/<uuid:service_id>/suspend', methods=['POST'])
@requires_admin_auth()
def suspend_service(service_id):
    """
    Suspending a service will mark the service as inactive and revoke API keys.
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if service.active:
        dao_suspend_service(service.id)

    return '', 204


@service_blueprint.route('/<uuid:service_id>/resume', methods=['POST'])
@requires_admin_auth()
def resume_service(service_id):
    """
    Resuming a service that has been suspended will mark the service as active.
    The service will need to re-create API keys
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if not service.active:
        dao_resume_service(service.id)

    return '', 204


@service_blueprint.route('/<uuid:service_id>/notifications/templates_usage/monthly', methods=['GET'])
@requires_admin_auth()
def get_monthly_template_usage(service_id):
    try:
        start_date, end_date = get_financial_year(int(request.args.get('year', 'NaN')))
        data = fetch_monthly_template_usage_for_service(start_date=start_date, end_date=end_date, service_id=service_id)
        stats = list()
        for i in data:
            stats.append(
                {
                    'template_id': str(i.template_id),
                    'name': i.name,
                    'type': i.template_type,
                    'month': i.month,
                    'year': i.year,
                    'count': i.count,
                    'is_precompiled_letter': i.is_precompiled_letter,
                }
            )

        return jsonify(stats=stats), 200
    except ValueError:
        raise InvalidRequest('Year must be a number', status_code=400)


@service_blueprint.route('/<uuid:service_id>/send-notification', methods=['POST'])
@requires_admin_auth()
def create_one_off_notification(service_id):
    resp = send_one_off_notification(service_id, request.get_json())
    return jsonify(resp), 201


@service_blueprint.route('/<uuid:service_id>/organisation', methods=['GET'])
@requires_admin_auth()
def get_organisation_for_service(service_id):
    organisation = dao_get_organisation_by_service_id(service_id=service_id)
    return jsonify(organisation.serialize() if organisation else {}), 200


@service_blueprint.route('/unique', methods=['GET'])
@requires_admin_auth()
def is_service_name_unique():
    service_id, name, email_from = check_request_args(request)

    stmt = select(Service).where(Service.name == name)
    name_exists = db.session.scalars(stmt).first()

    stmt = select(Service).where(Service.email_from == email_from, Service.id != service_id)
    email_from_exists = db.session.scalar(stmt)

    result = not (name_exists or email_from_exists)
    return jsonify(result=result), 200


@service_blueprint.route('/<uuid:service_id>/data-retention', methods=['GET'])
@requires_admin_auth()
def get_data_retention_for_service(service_id):
    data_retention_list = fetch_service_data_retention(service_id)
    return jsonify([data_retention.serialize() for data_retention in data_retention_list]), 200


@service_blueprint.route('/<uuid:service_id>/data-retention/notification-type/<notification_type>', methods=['GET'])
@requires_admin_auth()
def get_data_retention_for_service_notification_type(
    service_id,
    notification_type,
):
    data_retention = fetch_service_data_retention_by_notification_type(service_id, notification_type)
    return jsonify(data_retention.serialize() if data_retention else {}), 200


@service_blueprint.route('/<uuid:service_id>/data-retention/<uuid:data_retention_id>', methods=['GET'])
@requires_admin_auth()
def get_data_retention_for_service_by_id(
    service_id,
    data_retention_id,
):
    data_retention = fetch_service_data_retention_by_id(service_id, data_retention_id)
    return jsonify(data_retention.serialize() if data_retention else {}), 200


@service_blueprint.route('/<uuid:service_id>/data-retention', methods=['POST'])
@requires_admin_auth()
def create_service_data_retention(service_id):
    form = validate(request.get_json(), add_service_data_retention_request)
    try:
        new_data_retention = insert_service_data_retention(
            service_id=service_id,
            notification_type=form.get('notification_type'),
            days_of_retention=form.get('days_of_retention'),
        )
    except IntegrityError:
        raise InvalidRequest(
            message='Service already has data retention for {} notification type'.format(form.get('notification_type')),
            status_code=400,
        )

    return jsonify(result=new_data_retention.serialize()), 201


@service_blueprint.route('/<uuid:service_id>/data-retention/<uuid:data_retention_id>', methods=['POST'])
@requires_admin_auth()
def modify_service_data_retention(
    service_id,
    data_retention_id,
):
    form = validate(request.get_json(), update_service_data_retention_request)

    update_count = update_service_data_retention(
        service_data_retention_id=data_retention_id,
        service_id=service_id,
        days_of_retention=form.get('days_of_retention'),
    )
    if update_count == 0:
        raise InvalidRequest(
            message='The service data retention for id: {} was not found for service: {}'.format(
                data_retention_id, service_id
            ),
            status_code=404,
        )

    return '', 204


@service_blueprint.route('/monthly-data-by-service')
@requires_admin_auth()
def get_monthly_notification_data_by_service():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    result = fact_notification_status_dao.fetch_monthly_notification_statuses_per_service(start_date, end_date)

    return jsonify(result)


@service_blueprint.route('/<uuid:service_id>/smtp', methods=['DELETE'])
@requires_admin_auth()
def delete_smtp_relay(service_id):
    service = dao_fetch_service_by_id(service_id)

    if service.smtp_user is not None:
        smtp_remove(service.smtp_user)
        service.smtp_user = None
        dao_update_service(service)
        return jsonify(True), 201
    else:
        raise InvalidRequest(message='SMTP user does not exist', status_code=500)


@service_blueprint.route('/<uuid:service_id>/smtp', methods=['GET'])
@requires_admin_auth()
def get_smtp_relay(service_id):
    service = dao_fetch_service_by_id(service_id)
    if service.smtp_user is not None:
        credentials = {
            'domain': service.smtp_user.split('-')[0],
            'name': current_app.config['AWS_SES_SMTP'],
            'port': '465',
            'tls': 'Yes',
            'username': smtp_get_user_key(service.smtp_user),
        }
        return jsonify(credentials), 200
    else:
        return jsonify({}), 200


@service_blueprint.route('/<uuid:service_id>/smtp', methods=['POST'])
@requires_admin_auth()
def create_smtp_relay(service_id):
    service = dao_fetch_service_by_id(service_id)

    alphabet = '1234567890abcdefghijklmnopqrstuvwxyz'

    if service.smtp_user is None:
        user_id = generate(alphabet, size=7)
        credentials = smtp_add(user_id)
        service.smtp_user = credentials['iam']
        dao_update_service(service)
        return jsonify(credentials), 201
    else:
        raise InvalidRequest(message='SMTP user already exists', status_code=500)


def check_request_args(request):
    service_id = request.args.get('service_id')
    name = request.args.get('name', None)
    email_from = request.args.get('email_from', None)
    errors = []
    if not service_id:
        errors.append({'service_id': [CAN_T_BE_EMPTY_ERROR_MESSAGE]})
    if not name:
        errors.append({'name': [CAN_T_BE_EMPTY_ERROR_MESSAGE]})
    if not email_from:
        errors.append({'email_from': [CAN_T_BE_EMPTY_ERROR_MESSAGE]})
    if errors:
        raise InvalidRequest(errors, status_code=400)
    return service_id, name, email_from
