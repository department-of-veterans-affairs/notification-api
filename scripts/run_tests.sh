#!/bin/bash
#
# Run project tests
#
# NOTE: This script expects to be run from the project root with
# ./scripts/run_tests.sh

set -o pipefail

function display_result {
  RESULT=$1
  EXIT_STATUS=$2
  TEST=$3

  if [ $RESULT -ne 0 ]; then
    echo -e "\033[31m$TEST failed\033[0m"
    exit $EXIT_STATUS
  else
    echo -e "\033[32m$TEST passed\033[0m"
  fi
}

flake8 .
display_result $? 1 "Code style check"

# Run tests with four concurrent threads.  Also see the configuration in ../pytest.ini and ../setup.cfg.
# https://docs.pytest.org/en/stable/reference/customize.html
pytest --disable-pytest-warnings --cov=app --cov-report=term-missing tests/app/celery/test_nightly_tasks.py --junitxml=test_results.xml -n4 -v --maxfail=10
display_result $? 2 "Unit tests"