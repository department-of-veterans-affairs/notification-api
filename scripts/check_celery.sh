#!/bin/sh

set -e

function get_celery_pids {
  # First, get the PID from the celery.pid file
  MAIN_PID=$(cat /tmp/celery.pid)

  # Check if the main process is ddtrace-run or Celery directly
  if pstree -p ${MAIN_PID} | grep -q 'ddtrace'; then
    # If ddtrace-run is present, navigate to the child process
    APP_PIDS=$(pstree -p ${MAIN_PID} | sed 's/.*-ddtrace(\([0-9]*\)).*-celery(\([0-9]*\)).*/\2/')
  else
    # If no ddtrace-run, assume the main process is Celery
    APP_PIDS=$(pstree -p ${MAIN_PID} | sed 's/.*-celery(\([0-9]*\)).*/\1/')
  fi

  echo "Here are the APP_PIDS: ${APP_PIDS}"
}

function ensure_celery_is_running {
  if [ "${APP_PIDS}" = "" ]; then
    echo "There are no celery processes running, this container is bad"
    exit 1
  fi

  for APP_PID in ${APP_PIDS}; do
      kill -0 ${APP_PID} 2>/dev/null || return 1
  done
}

get_celery_pids

ensure_celery_is_running