import os
from flask import Blueprint, url_for, make_response, redirect
from authlib.jose import jwt

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
    resp = oauth.github.get('/user', token=github_token)
    resp.raise_for_status()

    # do something with the token and profile
    # profile = resp.json()
    # user_url = profile['url']
    # html_user_url = profile['html_url']
    # orgs_url = profile['organizations_url']

    # returns empty []
    # orgs = oauth.github.get(orgs_url, token=github_token).json()

    # generate new token to set in cookie, authlib comes with jose module
    header = {'alg': 'HS256', 'typ': 'JWT'}
    payload = {'iss': 'Authlib', 'sub': '123'}
    key = os.getenv('TEST_SECRET')
    test_token = jwt.encode(header, payload, key)

    response = make_response(redirect('http://localhost:3000'))
    response.set_cookie('token', 'hello')
    response.set_cookie('test_token', test_token)
    return response
