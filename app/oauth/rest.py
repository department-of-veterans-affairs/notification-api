import re

from flask import Blueprint, url_for, make_response, redirect, jsonify, current_app, request
from flask_cors.core import get_cors_options, set_cors_headers
from flask_jwt_extended import create_access_token, verify_jwt_in_request
from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt import ExpiredSignatureError

from app.dao.users_dao import get_user_by_email
from app.errors import register_errors
from app.oauth.oauth import oauth

oauth_blueprint = Blueprint('oauth', __name__, url_prefix='')
register_errors(oauth_blueprint)


@oauth_blueprint.route('/login', methods=['GET'])
def login():
    redirect_uri = url_for('oauth.authorize', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)


@oauth_blueprint.route('/authorize')
def authorize():
    github_token = oauth.github.authorize_access_token()
    resp = oauth.github.get('/user/emails', token=github_token)
    resp.raise_for_status()

    # filter for emails only simply for p.o.c. purposes
    emails = list(result['email'] for result in resp.json())
    user = None
    for email in emails:
        if re.search("(@thoughtworks.com)", email):
            user = get_user_by_email(email)

    response = make_response(redirect(current_app.config['UI_HOST_NAME']))
    response.set_cookie(
        current_app.config['JWT_ACCESS_COOKIE_NAME'],
        create_access_token(
            identity=user
        ),
        httponly=True
    )
    return response


@oauth_blueprint.route('/redeem-token', methods=['GET'])
def redeem_token():
    try:
        verify_jwt_in_request(locations='cookies')
    except (NoAuthorizationError, ExpiredSignatureError):
        response = make_response('', 204)
    else:
        cookie = request.cookies.get(current_app.config['JWT_ACCESS_COOKIE_NAME'])
        response = make_response(jsonify(cookie))

    cors_options = {'origins': current_app.config['UI_HOST_NAME'], 'supports_credentials': True}
    set_cors_headers(response, get_cors_options(current_app, cors_options))

    return response
