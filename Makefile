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

clean: ## Remove virtualenv directory and build articacts
	rm -rf node_modules cache target venv .coverage build tests/.cache

install-bandit:
	pip install bandit

check-vulnerabilities: install-bandit ## Scan code for vulnerabilities and issues
	bandit -c .bandit.yml -r app/ -l

install-safety:
	pip install safety

check-dependencies: install-safety ## Scan dependencies for security vulnerabilities
	# Ignored issues not described here are documented in requirements-app.txt.
	# 7 Nov 2023: 61601 is fixed with urllib3 >=1.26.17, which is currently limited by the botocore version.
	# 8 Nov 2023: 61657 & 61661 are fixed with aiohttp >=3.8.6.
	# 20 Nov 2023: 61893 is fixed with urllib3 >=1.26.18, which is currently limited by the botocore version.
	safety check -r requirements.txt --full-report -i 51668 -i 59234 -i 61601 -i 61657 -i 61661 -i 61893

.PHONY:
	help \
	generate-version-file \
	test \
	test-requirements \
	clean \
	check-vulnerabilities \
	check-dependencies
