#!/bin/sh

set -e

PRIO_PID_LOG=/tmp/celery_priority.pid
ALL_PID_LOG=/tmp/celery_all.pid

post_execution_handler() {
  # Post Execution
  echo "Start gracefull worker shutdown..."
  # Gracefully shutdown workers
  kill -TERM "$WORKER_PRIO_PID"
  kill -TERM "$WORKER_ALL_PID"

  # Wait for them to shut down, then cleanup the PID files
  wait "$WORKER_PRIO_PID" && rm -f $PRIO_PID_LOG
  wait "$WORKER_ALL_PID" && rm -f $ALL_PID_LOG
  echo "...Workers shut down gracefully"
  exit 143; # 128 + 15 -- SIGTERM
}

# Look for SIGTERM
trap post_execution_handler SIGTERM

echo "Start the Priority queue worker";
# rm in case of manual shutdown (local)
rm -f $PRIO_PID_LOG
ddtrace-run celery -A run_celery.notify_celery worker -n priority --pidfile="$PRIO_PID_LOG" --loglevel=INFO --concurrency=$CELERY_CONCURRENCY -Q send-sms-tasks,send-email-tasks,lookup-contact-info-tasks,lookup-va-profile-id-tasks &
WORKER_PRIO_PID=$!
echo "Worker: Priority PID: $WORKER_PRIO_PID"

echo "Start the All queue worker";
# rm in case of manual shutdown (local)
rm -f $ALL_PID_LOG
ddtrace-run celery -A run_celery.notify_celery worker -n all --pidfile="$ALL_PID_LOG" --loglevel=INFO --concurrency=$CELERY_CONCURRENCY &
WORKER_ALL_PID=$!
echo "Worker: All PID: $WORKER_ALL_PID"

# Script/container runs as long as these two are running
wait "$WORKER_PRIO_PID"
wait "$WORKER_ALL_PID"
