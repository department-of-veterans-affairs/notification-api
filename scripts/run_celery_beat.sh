#!/bin/sh

set -e

ddtrace-run celery -A run_celery.notify_celery beat --loglevel=INFO
