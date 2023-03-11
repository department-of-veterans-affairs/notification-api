#!/usr/bin/env python
from __future__ import print_function
from ddtrace import patch_all
from ddtrace.profiling import Profiler
import os

import sentry_sdk

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
#This starts the Datadog profiler
#I chose to add the environment variables to the dockerfile, 
#for optimal reporting on the Datadog side, 
#such as seeing performance distinguisment between environments and app versions
prof = Profiler(
    env=os.environ.get("DD_ENV"),  # use the DD_ENV environment variable, or None if it's not set
    service=os.environ.get("DD_SERVICE"),  # use the DD_SERVICE environment variable, or None if it's not set
    version=os.environ.get("DD_VERSION"),  # use the DD_VERSION environment variable, or None if it's not set
)
prof.start()  # Should be as early as possible, eg before other imports, to ensure everything is profiled
