import re

from flask import Blueprint, url_for, make_response, redirect
from flask_jwt_extended import create_access_token

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

    response = make_response(redirect('http://localhost:3000'))
    response.set_cookie(
        'token',
        create_access_token(
            identity=user.serialize()
        )
    )
    return response
