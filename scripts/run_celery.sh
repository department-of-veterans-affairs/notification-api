#!/bin/sh

set -e

# Necessary to run as exec so the PID is transferred to Celery for the `SIGTERM` sent from ECS

ddtrace-run celery -A run_celery.notify_celery worker -n priority --pidfile="/tmp/celery_priority.pid" --loglevel=INFO --concurrency=$CELERY_CONCURRENCY -Q send-sms-tasks,send-email-tasks,lookup-contact-info-tasks,lookup-va-profile-id-tasks &
ddtrace-run celery -A run_celery.notify_celery worker -n all --pidfile="/tmp/celery_all.pid" --loglevel=INFO --concurrency=$CELERY_CONCURRENCY

