"""
Flask Blueprint for /internal endpoint that supports the following routes:
    POST /internal/generic_one - logs the request and returns a 200 response
    POST /internal/generic_two - logs the request and returns a 200 response
"""

from flask import Blueprint, current_app, jsonify, request


internal_blueprint = Blueprint('internal', __name__, url_prefix='/internal')


@internal_blueprint.route('/generic_one', methods=['POST'])
def generic_one():
    """
    Logs the request and returns a 200 response.
    """
    current_app.logger.info('Received request: %s', request.json)

    return jsonify({'message': 'Request received'})


@internal_blueprint.route('/generic_two', methods=['POST'])
def generic_two():
    """
    Logs the request and returns a 200 response.
    """
    current_app.logger.info('Received request: %s', request.json)
    current_app.logger.info('Requeset %s', request)
    return jsonify({'message': 'Request received'})
