#! /bin/sh

set -e

grep_string="run_celery.notify_celery\ worker"
celery_pid_count=$(ps aux | grep -E run_celery.notify_celery\ worker | grep -v grep | wc -l)

TOTAL_CELERY_PIDS=$((CELERY_CONCURRENCY + 1))

if [ $celery_pid_count -ne TOTAL_CELERY_PIDS ]; then
  echo -e "There are an incorrect number of Celery PIDs: $celery_pid_count"
  exit 1
else
  echo "Celery health check okay"
fi
