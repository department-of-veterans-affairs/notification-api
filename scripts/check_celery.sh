#! /bin/sh

set -e

grep_string="run_celery.notify_celery\ worker"
celery_pid_count=$(ps aux | grep -E run_celery.notify_celery\ worker | grep -v grep | wc -l)

echo "$CELERY_CONCURRENCY"

CELERY_CONCURRENCY_INT=$(echo "$CELERY_CONCURRENCY" | tr -d '[[:space:]]')

if ! [ "$CELERY_CONCURRENCY_INT" -eq "$CELERY_CONCURRENCY_INT" ] 2>/dev/null; then
  echo "CELERY_CONCURRENCY is not a valid integer: $CELERY_CONCURRENCY"
  exit 1
fi

TOTAL_CELERY_PIDS=$((CELERY_CONCURRENCY_INT + 1))

if [ $celery_pid_count -ne $TOTAL_CELERY_PIDS ]; then
  echo -e "There are an incorrect number of Celery PIDs: $celery_pid_count"
  exit 1
else
  echo "Celery health check okay"
fi
