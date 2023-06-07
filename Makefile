.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

generate-version-file: ## Generates the app version file
	@echo -e "__git_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"" > ${APP_VERSION_FILE}

test:
	./scripts/run_tests.sh
	rm -rf .pytest_cache test_results.xml

user_flows: generate-version-file ## Run tests
	./scripts/run_user_flows.sh

clean: ## Remove virtualenv directory and build articacts
	rm -rf node_modules cache target venv .coverage build tests/.cache

install-bandit:
	pip install bandit

check-vulnerabilities: install-bandit ## Scan code for vulnerabilities and issues
	bandit -c .bandit.yml -r app/ -l

install-safety:
	pip install safety

check-dependencies: install-safety ## Scan dependencies for security vulnerabilities
    # Issues 53325 and 53326 affect Werkzeug < 2.2.3.  Werkzeug is a subdependency of Flask.
	# The remaining ignored issues are documented in requirements-app.txt.
	safety check -r requirements.txt --full-report -i 42497 -i 42498 -i 43738 -i 51668 -i 53325 -i 53326 -i 55261

.PHONY:
	help \
	generate-version-file \
	test \
	user_flows \
	daily_user_flows \
	test-requirements \
	clean \
	check-vulnerabilities \
	check-dependencies
