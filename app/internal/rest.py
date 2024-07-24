"""
Flask Blueprint for /internal endpoint that supports the following routes:
    POST /internal/generic_one - logs the request and returns a 200 response
    POST /internal/generic_two - logs the request and returns a 200 response
"""

from contextlib import suppress

from flask import Blueprint, current_app, jsonify, request


internal_blueprint = Blueprint('internal', __name__, url_prefix='/internal')


@internal_blueprint.route('/<generic>', methods=['POST', 'GET'])
def handler(generic):
    """
    Logs the request and returns a 200 response.
    """
    status_code = 200
    request_attrs = (
        'headers',
        'method',
        'root_path',
        'path',
        'query_string',
        'json',
        'url_rule',
        'trace_id',
    )
    for attr in request_attrs:
        with suppress(Exception):
            current_app.logger.info('Request %s: %s', attr.upper(), getattr(request, attr))

    if request.method == 'GET':
        response_body = f'GET request received for endpoint {request.full_path}'
    else:
        response_body = jsonify({'request_received': request.json})

    return response_body, status_code
