"""
Flask Blueprint for internal endpoints of the form /internal/<generic>.
  - GET requests return a string with the full path of the request and a 200 status code.
  - POST requests return a JSON object with the request data and a 200 status code.

Logging is performed for the following request attributes:
    - headers
    - method
    - root_path
    - path
    - query_string
    - json
    - url_rule
    - trace_id
"""

from contextlib import suppress

from flask import Blueprint, current_app, request


internal_blueprint = Blueprint('internal', __name__, url_prefix='/internal')


@internal_blueprint.route('/<generic>', methods=['POST', 'GET'])
def handler(generic):
    """
    Logs the request and returns a 200 response.

    Args:
        generic (str): A generic endpoint from the URL.

    Returns:
        tuple: A tuple containing the response body and status code. For GET requests, the response body is
          a string with the endpoint. For POST requests, the response body is a JSON object with the request
          data. The status code is always 200.

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
            current_app.logger.info('Generic Internal Request %s: %s', attr.upper(), getattr(request, attr))

    if request.method == 'GET':
        response_body = f'GET request received for endpoint {request.full_path}'
    else:
        response_body = {generic: request.json}

    return response_body, status_code
