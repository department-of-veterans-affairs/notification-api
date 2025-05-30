from flask import Blueprint, jsonify, request

from app.schemas import provider_details_schema, provider_details_history_schema
from app.dao.provider_details_dao import (
    dao_update_provider_details,
    dao_get_provider_stats,
    dao_get_provider_versions,
)
from app.dao.users_dao import get_user_by_id
from app.db import db
from app.errors import register_errors, InvalidRequest
from app.models import ProviderDetails

provider_details = Blueprint('provider_details', __name__)
register_errors(provider_details)


@provider_details.route('', methods=['GET'])
def get_providers():
    data = dao_get_provider_stats()

    provider_details = [
        {
            'id': row.id,
            'display_name': row.display_name,
            'identifier': row.identifier,
            'priority': row.priority,
            'load_balancing_weight': row.load_balancing_weight,
            'notification_type': row.notification_type,
            'active': row.active,
            'updated_at': row.updated_at,
            'supports_international': row.supports_international,
            'created_by_name': row.created_by_name,
            'current_month_billable_sms': row.current_month_billable_sms,
        }
        for row in data
    ]

    return jsonify(provider_details=provider_details)


@provider_details.route('/<uuid:provider_details_id>', methods=['GET'])
def get_provider_by_id(provider_details_id):
    provider = db.session.get(ProviderDetails, provider_details_id)
    data = provider_details_schema.dump(provider)
    return jsonify(provider_details=data)


@provider_details.route('/<uuid:provider_details_id>/versions', methods=['GET'])
def get_provider_versions(provider_details_id):
    versions = dao_get_provider_versions(provider_details_id)
    data = provider_details_history_schema.dump(versions, many=True)
    return jsonify(data=data)


@provider_details.route('/<uuid:provider_details_id>', methods=['POST'])
def update_provider_details(provider_details_id):
    valid_keys = {'priority', 'created_by', 'active', 'load_balancing_weight'}
    req_json = request.get_json()

    invalid_keys = req_json.keys() - valid_keys
    if invalid_keys:
        message = 'Not permitted to be updated'
        errors = {key: [message] for key in invalid_keys}
        raise InvalidRequest(errors, status_code=400)

    provider = db.session.get(ProviderDetails, provider_details_id)

    # Handle created_by differently due to how history entry is created
    if 'created_by' in req_json:
        user = get_user_by_id(req_json['created_by'])
        provider.created_by_id = user.id
        req_json.pop('created_by')

    for key in req_json:
        setattr(provider, key, req_json[key])
    dao_update_provider_details(provider)

    return jsonify(provider_details=provider_details_schema.dump(provider)), 200
