#!/usr/bin/env python

"""
This is the application entry point called from Dockerfile (for AWS environments) or from
scripts/run_app.sh via Dockerfile.local (for local containers).  It creates the Flask
application instance and calls create_app to configure this instance.
"""

from __future__ import print_function
import os

import sentry_sdk
from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration
from werkzeug.middleware.proxy_fix import ProxyFix

# Imports out of order to avoid issues with error 'Missing environment sid for type'
from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa E402
from app.version import __git_commit__  # noqa E402

sentry_sdk.init(
    dsn=os.environ.get('SENTRY_URL', ''),
    integrations=[FlaskIntegration()],
    release=__git_commit__,
)

application = Flask('app')
application.wsgi_app = ProxyFix(application.wsgi_app)
create_app(application)
