import base64
import json
from flask import Blueprint, current_app, jsonify, request

from app import aws_pinpoint_client
from app.celery.exceptions import NonRetryableException
from app.clients.sms import SmsStatusRecord
from app.celery.process_delivery_status_result_tasks import get_notification_platform_status
from app.celery.process_pinpoint_v2_receipt_tasks import process_pinpoint_v2_receipt_results
from app.config import QueueNames

from app.errors import register_errors


pinpoint_v2_blueprint = Blueprint('pinpoint_v2', __name__)
register_errors(pinpoint_v2_blueprint)


@pinpoint_v2_blueprint.route('/delivery-status/sms/pinpointv2', methods=['POST'])
def handler():
    """
    Handle Pinpoint SMS Voice V2 delivery status updates.
    Decodes request body and processes each record through Celery.

    Returns:
        tuple: JSON response body and HTTP status code 200.
    """

    request_data = request.get_json()
    decoded_json = json.loads(base64.b64decode(request_data['Message']).decode('utf-8'))

    current_app.logger.debug('PinpointV2 delivery-status Request: %s', decoded_json)

    records = decoded_json.get('Records', [])

    for record in records:
        try:
            notification_platform_status: SmsStatusRecord = get_notification_platform_status(
                aws_pinpoint_client, record
            )
        except NonRetryableException as e:
            current_app.logger.error(
                'Validation for Pinpoint SMS Voice V2 records failed: %s | Error: %s',
                record.get('messageId', 'unknown messageId'),
                str(e),
            )
            continue
        process_pinpoint_v2_receipt_results.apply_async(
            [notification_platform_status, record.get('eventTimestamp')],
            queue=QueueNames.NOTIFY,
            serializer='pickle',
        )

    return jsonify({'status': 'received'}), 200
