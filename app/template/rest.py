import base64
from datetime import datetime
from io import BytesIO

import botocore
from pypdf.errors import PdfReadError
from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
)
from flask_jwt_extended import current_user
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.pdf import extract_page_from_pdf
from notifications_utils.template import SMSMessageTemplate
from requests import post as requests_post
from sqlalchemy.orm.exc import NoResultFound
from notifications_utils.template import HTMLEmailTemplate

from app.authentication.auth import requires_admin_auth_or_user_in_service, requires_user_in_service_or_admin
from app.communication_item import validate_communication_items
from app.constants import HTTP_TIMEOUT, LETTER_TYPE, SECOND_CLASS, SMS_TYPE
from app.dao.fact_notification_status_dao import fetch_template_usage_for_service_with_given_template
from app.dao.notifications_dao import get_notification_by_id
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.template_folder_dao import dao_get_template_folder_by_id_and_service_id
from app.dao.templates_dao import (
    dao_update_template,
    dao_create_template,
    dao_redact_template,
    dao_get_template_by_id_and_service_id,
    dao_get_all_templates_for_service,
    dao_get_template_versions,
    dao_update_template_reply_to,
    dao_get_template_by_id,
    get_precompiled_letter_template,
)
from app.errors import InvalidRequest, register_errors
from app.feature_flags import is_feature_enabled, FeatureFlag
from app.letters.utils import get_letter_pdf
from app.models import Template
from app.notifications.validators import service_has_permission, check_reply_to, template_name_already_exists_on_service
from app.provider_details import validate_providers
from app.schema_validation import validate
from app.schemas import template_schema, template_history_schema
from app.template.template_schemas import post_create_template_schema, template_stats_request
from app.utils import get_template_instance, get_public_notify_type_text

template_blueprint = Blueprint('template', __name__, url_prefix='/service/<uuid:service_id>/template')

register_errors(template_blueprint)


def _content_count_greater_than_limit(
    content,
    template_type,
):
    if template_type != SMS_TYPE:
        return False
    template = SMSMessageTemplate({'content': content, 'template_type': template_type})
    return template.content_count > SMS_CHAR_COUNT_LIMIT


def validate_parent_folder(template_json):
    if template_json.get('parent_folder_id'):
        try:
            return dao_get_template_folder_by_id_and_service_id(
                template_folder_id=template_json.pop('parent_folder_id'), service_id=template_json['service']
            )
        except NoResultFound:
            raise InvalidRequest('parent_folder_id not found', status_code=400)
    else:
        return None


@template_blueprint.route('', methods=['POST'])
@requires_admin_auth_or_user_in_service(required_permission='edit_templates')
def create_template(service_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    # permissions needs to be placed here otherwise marshmallow will interfere with versioning
    permissions = fetched_service.permissions

    request_body = request.get_json()
    if current_user:
        request_body['created_by'] = str(current_user.id)

    template_json = validate(request_body, post_create_template_schema)

    validate_communication_items.validate_communication_item_id(template_json)
    validate_providers.validate_template_providers(template_json)

    folder = validate_parent_folder(template_json=template_json)
    new_template = Template.from_json(template_json, folder)

    if is_feature_enabled(FeatureFlag.CHECK_TEMPLATE_NAME_EXISTS_ENABLED) and template_name_already_exists_on_service(
        service_id, new_template.name
    ):
        message = 'Template name already exists in service. Please change template name.'
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)

    # TODO #1410 clean up validator, use class method instead.
    if not service_has_permission(new_template.template_type, permissions):
        message = 'Creating {} templates is not allowed'.format(get_public_notify_type_text(new_template.template_type))
        errors = {'template_type': [message]}
        raise InvalidRequest(errors, 403)

    if not new_template.postage and new_template.template_type == LETTER_TYPE:
        new_template.postage = SECOND_CLASS

    new_template.service = fetched_service

    over_limit = _content_count_greater_than_limit(new_template.content, new_template.template_type)
    if over_limit:
        message = 'Content has a character count greater than the limit of {}'.format(SMS_CHAR_COUNT_LIMIT)
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)

    check_reply_to(service_id, new_template.reply_to, new_template.template_type)

    dao_create_template(new_template)

    return jsonify(data=template_schema.dump(new_template)), 201


@template_blueprint.route('/<uuid:template_id>', methods=['POST'])
@requires_admin_auth_or_user_in_service(required_permission='edit_templates')
def update_template(
    service_id,
    template_id,
):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)

    if not service_has_permission(fetched_template.template_type, fetched_template.service.permissions):
        message = 'Updating {} templates is not allowed'.format(
            get_public_notify_type_text(fetched_template.template_type)
        )
        errors = {'template_type': [message]}

        raise InvalidRequest(errors, 403)

    data = request.get_json()

    if data.get('redact_personalisation') is True:
        # Don't update anything else.
        return redact_template(fetched_template, data)

    if 'reply_to' in data:
        check_reply_to(service_id, data.get('reply_to'), fetched_template.template_type)
        updated = dao_update_template_reply_to(template_id=template_id, reply_to=data.get('reply_to'))
        return jsonify(data=template_schema.dump(updated)), 200

    current_data = template_schema.dump(fetched_template)
    updated_template = template_schema.dump(fetched_template)
    updated_template.update(data)

    if (
        is_feature_enabled(FeatureFlag.CHECK_TEMPLATE_NAME_EXISTS_ENABLED)
        and data.get('name')
        and template_name_already_exists_on_service(service_id, data.get('name'))
    ):
        message = 'Template name already exists in service. Please change template name.'
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)

    # Check if there is a change to make.
    if _template_has_not_changed(current_data, updated_template):
        return jsonify(data=updated_template), 200

    over_limit = _content_count_greater_than_limit(updated_template['content'], fetched_template.template_type)
    if over_limit:
        message = 'Content has a character count greater than the limit of {}'.format(SMS_CHAR_COUNT_LIMIT)
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)

    update_dict = template_schema.load(updated_template)
    dao_update_template(update_dict)
    return jsonify(data=template_schema.dump(update_dict)), 200


@template_blueprint.route('/precompiled', methods=['GET'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def get_precompiled_template_for_service(service_id):
    template = get_precompiled_letter_template(service_id)
    template_dict = template_schema.dump(template)

    return jsonify(template_dict), 200


@template_blueprint.route('', methods=['GET'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def get_all_templates_for_service(service_id):
    templates = dao_get_all_templates_for_service(service_id=service_id)
    data = template_schema.dump(templates, many=True)
    return jsonify(data=data)


@template_blueprint.route('/<uuid:template_id>', methods=['GET'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def get_template_by_id_and_service_id(
    service_id,
    template_id,
):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)
    data = template_schema.dump(fetched_template)
    return jsonify(data=data)


@template_blueprint.route('/<uuid:template_id>/preview', methods=['GET'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def preview_template_by_id_and_service_id(
    service_id,
    template_id,
):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)
    data = template_schema.dump(fetched_template)
    template_object = get_template_instance(data, values=request.args.to_dict())

    if template_object.missing_data:
        raise InvalidRequest(
            {'template': ['Missing personalisation: {}'.format(', '.join(template_object.missing_data))]},
            status_code=400,
        )

    data['subject'], data['content'] = template_object.subject, str(template_object)

    return jsonify(data)


@template_blueprint.route('/<template_id>/preview-html', methods=['GET'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def get_html_template(
    service_id,
    template_id,
):
    template_dict = dao_get_template_by_id(template_id).__dict__

    html_email = HTMLEmailTemplate(template_dict, values={}, preview_mode=True)

    return jsonify(previewContent=str(html_email))


@template_blueprint.route('/preview', methods=['POST'])
@requires_user_in_service_or_admin(required_permission='manage_templates')
def generate_html_preview_for_content(service_id):
    data = request.get_json()

    html_email = HTMLEmailTemplate({'content': data['content'], 'subject': ''}, values={}, preview_mode=True)

    return str(html_email), 200, {'Content-Type': 'text/html; charset=utf-8'}


@template_blueprint.route('/generate-preview', methods=['POST'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def generate_html_preview_for_template_content(service_id):
    data = request.get_json()

    html_email = HTMLEmailTemplate({'content': data['content'], 'subject': ''}, values={}, preview_mode=True)

    return str(html_email), 200, {'Content-Type': 'text/html; charset=utf-8'}


@template_blueprint.route('/<uuid:template_id>/version/<int:version>')
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def get_template_version(
    service_id,
    template_id,
    version,
):
    data = template_history_schema.dump(
        dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id, version=version)
    )

    return jsonify(data=data)


@template_blueprint.route('/<uuid:template_id>/versions')
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def get_template_versions(
    service_id,
    template_id,
):
    data = template_history_schema.dump(
        dao_get_template_versions(service_id=service_id, template_id=template_id), many=True
    )
    return jsonify(data=data)


def _template_has_not_changed(
    current_data,
    updated_template,
):
    keys = (
        'name',
        'content',
        'subject',
        'archived',
        'process_type',
        'postage',
        'provider_id',
        'communication_item_id',
        'reply_to_email',
        'reply_to_text',
        'onsite_notification',
    )

    try:
        if any(current_data[key] != updated_template[key] for key in keys):
            return False
    except KeyError:
        return False
    return True


def redact_template(
    template,
    data,
):
    # we also don't need to check what was passed in redact_personalisation - its presence in the dict is enough.
    if 'created_by' not in data:
        message = 'Field is required'
        errors = {'created_by': [message]}
        raise InvalidRequest(errors, status_code=400)

    # if it's already redacted, then just return 200 straight away.
    if not template.redact_personalisation:
        dao_redact_template(template, data['created_by'])
    return 'null', 200


@template_blueprint.route('/preview/<uuid:notification_id>/<file_type>', methods=['GET'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def preview_letter_template_by_notification_id(
    service_id,
    notification_id,
    file_type,
):
    if file_type not in ('pdf', 'png'):
        raise InvalidRequest({'content': ['file_type must be pdf or png']}, status_code=400)

    page = request.args.get('page')

    notification = get_notification_by_id(notification_id)

    template = dao_get_template_by_id(notification.template_id)

    if template.is_precompiled_letter:
        try:
            pdf_file = get_letter_pdf(notification)

        except botocore.exceptions.ClientError as e:
            raise InvalidRequest(
                'Error extracting requested page from PDF file for notification_id {} type {} {}'.format(
                    notification_id, type(e), e
                ),
                status_code=500,
            )

        content = base64.b64encode(pdf_file).decode('utf-8')
        overlay = request.args.get('overlay')
        page_number = page if page else '1'

        if overlay:
            path = '/precompiled/overlay.{}'.format(file_type)
            query_string = '?page_number={}'.format(page_number) if file_type == 'png' else ''
            content = pdf_file
        elif file_type == 'png':
            query_string = '?hide_notify=true' if page_number == '1' else ''
            path = '/precompiled-preview.png'
        else:
            path = None

        if file_type == 'png':
            try:
                pdf_page = extract_page_from_pdf(BytesIO(pdf_file), int(page_number) - 1)
                content = pdf_page if overlay else base64.b64encode(pdf_page).decode('utf-8')
            except PdfReadError as e:
                raise InvalidRequest(
                    'Error extracting requested page from PDF file for notification_id {} type {} {}'.format(
                        notification_id, type(e), e
                    ),
                    status_code=500,
                )

        if path:
            url = current_app.config['TEMPLATE_PREVIEW_API_HOST'] + path + query_string
            response_content = _get_png_preview_or_overlaid_pdf(url, content, notification.id, json=False)
        else:
            response_content = content
    else:
        template_for_letter_print = {
            'id': str(notification.template_id),
            'subject': template.subject,
            'content': template.content,
            'version': str(template.version),
        }

        data = {
            'letter_contact_block': notification.reply_to_text,
            'template': template_for_letter_print,
            'values': notification.personalisation,
            'date': notification.created_at.isoformat(),
            'filename': None,
        }

        url = '{}/preview.{}{}'.format(
            current_app.config['TEMPLATE_PREVIEW_API_HOST'], file_type, '?page={}'.format(page) if page else ''
        )
        response_content = _get_png_preview_or_overlaid_pdf(url, data, notification.id, json=True)

    return jsonify({'content': response_content})


@template_blueprint.route('/<uuid:template_id>/stats', methods=['GET'])
@requires_admin_auth_or_user_in_service(required_permission='manage_templates')
def get_specific_template_usage_stats(
    service_id,
    template_id,
):
    start_date = None
    end_date = None

    if request.args:
        validate(request.args, template_stats_request)

        start_date = (
            datetime.strptime(request.args.get('start_date'), '%Y-%m-%d').date()
            if request.args.get('start_date')
            else None
        )
        end_date = (
            datetime.strptime(request.args.get('end_date'), '%Y-%m-%d').date() if request.args.get('end_date') else None
        )

    data = fetch_template_usage_for_service_with_given_template(
        service_id=service_id, template_id=template_id, start_date=start_date, end_date=end_date
    )
    stats = {}
    for i in data:
        stats[i.status] = i.count

    return jsonify(data=stats), 200


def _get_png_preview_or_overlaid_pdf(
    url,
    data,
    notification_id,
    json=True,
):
    if json:
        resp = requests_post(
            url,
            json=data,
            headers={'Authorization': 'Token {}'.format(current_app.config['TEMPLATE_PREVIEW_API_KEY'])},
            timeout=HTTP_TIMEOUT,
        )
    else:
        resp = requests_post(
            url,
            data=data,
            headers={'Authorization': 'Token {}'.format(current_app.config['TEMPLATE_PREVIEW_API_KEY'])},
            timeout=HTTP_TIMEOUT,
        )

    if resp.status_code != 200:
        raise InvalidRequest(
            'Error generating preview letter for {} Status code: {} {}'.format(
                notification_id, resp.status_code, resp.content
            ),
            status_code=500,
        )

    return base64.b64encode(resp.content).decode('utf-8')
