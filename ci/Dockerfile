# Python 3.10 is supported until October 2026.
# Alpine Linux 3.19 is supported until 1 November 2025
FROM python:3.10-alpine3.19 as builder

# ARG GIT_SHA


# REQUESTS_CA_BUNDLE is for the "requests" Python package.
#   https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification
ENV PYTHONDONTWRITEBYTECODE=1 \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PORT=6011 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1
    # PATH="$POETRY_HOME/bin:$PATH"
    # GIT_SHA=${GIT_SHA}

# Add poetry home location to path
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app

COPY . /app

# Install dependencies
RUN apk add --no-cache bash build-base git postgresql-dev g++ make libffi-dev libmagic libcurl python3-dev openssl-dev \
    curl-dev wget openssl

RUN bash scripts/import-va-certs.sh

# Generate the version file, app/version.py.  This overwrites the default file needed for local development.
# The safe.directory modification eliminates the error, "fatal: detected dubious ownership in repository at '/app'".
RUN git config --global --add safe.directory /app \
    && make generate-version-file

# # Arguments for this poetry install
ARG POETRY_ARGS

WORKDIR /opt

# copy only necessary files
COPY poetry.lock pyproject.toml .

# # RUN apk add --no-cache --virtual .build-deps gcc musl-dev rust cargo curl \
RUN apk add --no-cache --virtual .build-deps cargo curl gcc musl-dev rust \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && poetry install --no-root --no-ansi $POETRY_ARGS

# ########################################################################################################################

# Python 3.10 is supported until October 2026.
# Alpine Linux 3.19 is supported until 1 November 2025
FROM python:3.10-alpine3.19

ENV PYTHONDONTWRITEBYTECODE=1 \
    # https://flask.palletsprojects.com/en/2.2.x/config/?highlight=flask_debug#DEBUG
    FLASK_DEBUG="true" \
    PATH="/opt/.venv/bin:$PATH"

# copy the venv that was built from builder image
COPY --from=builder /app/app/version.py /app/app/version.py
COPY --from=builder /opt/.venv /opt/.venv
COPY --from=builder /usr/local/share/ca-certificates/ /usr/local/share/ca-certificates/
COPY --from=builder /usr/share/ca-certificates/ /usr/share/ca-certificates/

# Populate /etc/ssl/certs/ with symlinks to /usr/[local/]share/ca-certificates/ certs
RUN apk add --no-cache ca-certificates bash build-base libcurl openssl-dev \
    && adduser -h /app -D vanotify \
    && update-ca-certificates \
    && apk del --no-cache ca-certificates bash

RUN apk add --no-cache bash build-base libcurl openssl-dev

# Copy the host's build context directory (notification-api/) to the image's working directory (/app).
COPY --chown=vanotify . .

WORKDIR /app

USER vanotify

ENTRYPOINT ["./scripts/save_certificate.sh"]
CMD ["sh", "-c", "ddtrace-run gunicorn -c gunicorn_config.py application"]
