from flask import Blueprint, url_for, make_response, redirect

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
    oauth.github.authorize_access_token()
    # resp = oauth.github.get('user')
    # profile = resp.json()
    # do something with the token and profile
    response = make_response(redirect('http://localhost:3000'))
    response.set_cookie('token', 'hello')
    return response
