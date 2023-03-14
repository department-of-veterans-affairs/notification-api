#!/usr/bin/env python
from __future__ import print_function
from ddtrace import patch_all
from ddtrace.profiling import Profiler
import os

import sentry_sdk

#This starts the Datadog profiler, and should be before other imports, to ensure everything is profiled
prof = Profiler()
prof.start()

from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app

from dotenv import load_dotenv

load_dotenv()

sentry_sdk.init(
    dsn=os.environ.get('SENTRY_URL', ''),
    integrations=[FlaskIntegration()],
    release=os.environ.get('GIT_SHA', '')
)

application = Flask('app')
application.wsgi_app = ProxyFix(application.wsgi_app)
create_app(application)


# this starts the ddtrace tracer and configures it to the right port and URL
patch_all()
