from flask import Blueprint, request, jsonify, current_app

from app.config import QueueNames
from app.constants import EMAIL_TYPE, KEY_TYPE_NORMAL
from app.dao.invited_user_dao import save_invited_user, get_invited_user, get_invited_users_for_service
from app.dao.templates_dao import dao_get_template_by_id
from app.models import Service
from app.notifications.process_notifications import persist_notification, send_notification_to_queue
from app.schemas import invited_user_schema
from app.errors import register_errors
from app import db

invite = Blueprint('invite', __name__, url_prefix='/service/<service_id>/invite')

register_errors(invite)


# TODO - This function takes a "service_id" because it's part of the associated URL, but "service_id" is not used.
# This probably indicates that the URL should be different.  See #1103.
@invite.route('', methods=['POST'])
def create_invited_user(service_id):
    request_json = request.get_json()
    invited_user = invited_user_schema.load(request_json)
    invited_user_instance = save_invited_user(invited_user)

    template = dao_get_template_by_id(current_app.config['INVITATION_EMAIL_TEMPLATE_ID'])
    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=invited_user['email_address'],
        service_id=service.id,
        personalisation={
            'user_name': invited_user['from_user'].name,
            'service_name': invited_user['service'].name,
            'url': invited_user_url(
                invited_user_instance.id,
                request_json.get('invite_link_host'),
            ),
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=invited_user['from_user'].email_address,
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    invited_user_data = invited_user_schema.dump(invited_user)
    invited_user_data['id'] = invited_user_instance.id
    return jsonify(data=invited_user_data), 201


@invite.route('', methods=['GET'])
def get_invited_users_by_service(service_id):
    invited_users = get_invited_users_for_service(service_id)
    return jsonify(data=invited_user_schema.dump(invited_users, many=True)), 200


@invite.route('/<invited_user_id>', methods=['POST'])
def update_invited_user(
    service_id,
    invited_user_id,
):
    fetched = get_invited_user(service_id=service_id, invited_user_id=invited_user_id)
    current_data = dict(invited_user_schema.dump(fetched))
    current_data.update(request.get_json())
    fetched.status = current_data['status']
    save_invited_user(fetched)
    return jsonify(data=invited_user_schema.dump(fetched)), 200


def invited_user_url(
    invited_user_id,
    invite_link_host=None,
):
    from notifications_utils.url_safe_token import generate_token

    token = generate_token(str(invited_user_id), current_app.config['SECRET_KEY'], current_app.config['DANGEROUS_SALT'])

    if invite_link_host is None:
        invite_link_host = current_app.config['ADMIN_BASE_URL']

    return '{0}/invitation/{1}'.format(invite_link_host, token)
