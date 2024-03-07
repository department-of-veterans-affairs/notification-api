# Python 3.10 is supported until October 2026.
# Alpine Linux 3.19 is supported until 1 November 2025
FROM python:3.10-alpine3.19 as builder

ARG GIT_SHA=""


# REQUESTS_CA_BUNDLE is for the "requests" Python package.
#   https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification
ENV PYTHONDONTWRITEBYTECODE=1 \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PORT=6011 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1 \
    GIT_SHA=${GIT_SHA}

# Add poetry home location to path
ENV PATH="$POETRY_HOME/bin:$PATH"

COPY scripts/import-va-certs.sh .
COPY certs/* /usr/local/share/ca-certificates/
COPY .git .
COPY Makefile .
COPY app/version.py app/version.py
COPY poetry.lock pyproject.toml .

# Install dependencies
RUN apk add --no-cache bash build-base git postgresql-dev g++ make libffi-dev libmagic libcurl python3-dev openssl-dev \
    curl-dev wget openssl

RUN bash import-va-certs.sh

# Generate the version file, app/version.py.  This overwrites the default file needed for local development.
# The safe.directory modification eliminates the error, "fatal: detected dubious ownership in repository at '/app'".
RUN make generate-version-file

# # Arguments for this poetry install
ARG POETRY_ARGS

# # RUN apk add --no-cache --virtual .build-deps gcc musl-dev rust cargo curl \
RUN apk add --no-cache --virtual .build-deps cargo curl gcc musl-dev rust \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && poetry install --no-root --no-ansi $POETRY_ARGS

# # ########################################################################################################################

# # Python 3.10 is supported until October 2026.
# # Alpine Linux 3.19 is supported until 1 November 2025
FROM python:3.10-alpine3.19

ENV PYTHONDONTWRITEBYTECODE=1 \
    # https://flask.palletsprojects.com/en/2.2.x/config/?highlight=flask_debug#DEBUG
    FLASK_DEBUG="true" \
    PATH="/.venv/bin:$PATH"

COPY --chown=vanotify cd/ app/cd
COPY --chown=vanotify app/ app/app
COPY --chown=vanotify migrations/ app/migrations
COPY --chown=vanotify scripts/ app/scripts/

# Tests, using glob pattern to avoid copying if they are excluded from context
COPY test[s]/ app/tests

# copy the venv that was built from builder image
COPY --from=builder --chown=vanotify /app/version.py /app/app/version.py
COPY --from=builder --chown=vanotify /.venv /.venv
COPY --from=builder --chown=vanotify /usr/local/share/ca-certificates/* /usr/local/share/ca-certificates/
COPY --from=builder --chown=vanotify /usr/share/ca-certificates/* /usr/share/ca-certificates/

# Populate /etc/ssl/certs/ with symlinks to /usr/[local/]share/ca-certificates/ certs
RUN apk add --no-cache ca-certificates bash build-base libcurl openssl-dev \
    && adduser -h /app -D vanotify \
    && update-ca-certificates \
    && apk del --no-cache ca-certificates bash

RUN apk add --no-cache bash build-base libcurl openssl-dev

# # Copy the host's build context directory (notification-api/) to the image's working directory (/app).
# COPY --chown=vanotify . .

WORKDIR /app

USER vanotify

ENTRYPOINT ["./scripts/save_certificate.sh"]
CMD ["sh", "-c", "ddtrace-run gunicorn -c gunicorn_config.py application"]
