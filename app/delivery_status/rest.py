import base64
import json
from contextlib import suppress
from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import UnsupportedMediaType

from app import aws_pinpoint_client
from app.clients.sms import SmsStatusRecord
from app.celery.process_delivery_status_result_tasks import get_notification_platform_status
from app.celery.process_pinpoint_v2_receipts_tasks import process_pinpoint_v2_receipt_results


pinpoint_v2_blueprint = Blueprint('pinpoint_v2', __name__)


@pinpoint_v2_blueprint.route('/delivery-status/sms/pinpointv2', methods=['POST'])
def handler():
    """
    Handle Pinpoint SMS Voice V2 delivery status updates.
    Decodes request body and processes each record through Celery.

    Returns:
        tuple: JSON response body and HTTP status code 200.
    """
    # TODO 2497: using for debugging, need to remove
    request_attrs = (
        'method',
        'root_path',
        'path',
        'url_rule',
    )
    logs = [f'{attr.upper()}: {getattr(request, attr, None)}' for attr in request_attrs]

    with suppress(UnsupportedMediaType, Exception):
        logs.append(f'JSON: {request.get_json(silent=True)}')

    # TODO 2497: using for debugging, need to remove
    headers_string = ', '.join([f'{key}: {value}' for key, value in request.headers.items()])
    logs.append(f'HEADERS: {headers_string}')

    current_app.logger.info('PinpointV2 delivery-status request: %s', ' | '.join(logs))

    # TODO 2497: Add validation for request data
    request_data = request.get_json()
    decoded_json = json.loads(base64.b64decode(request_data['Message']).decode('utf-8'))

    records = decoded_json.get('Records', [])

    for record in records:
        notification_platform_status: SmsStatusRecord = get_notification_platform_status(aws_pinpoint_client, record)
        process_pinpoint_v2_receipt_results.apply_async([notification_platform_status, record.get('event_timestamp')])

    return jsonify({'status': 'received'}), 200
