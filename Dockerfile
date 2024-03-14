# Python 3.10 is supported until October 2026.
# Alpine Linux 3.19 is supported until 1 November 2025
FROM python:3.10-alpine3.19

ENV PYTHONDONTWRITEBYTECODE=1 \
    # https://flask.palletsprojects.com/en/2.2.x/config/?highlight=flask_debug#DEBUG
    FLASK_DEBUG="true"

RUN adduser -h /app -D vanotify
WORKDIR /app


RUN apk add --no-cache bash build-base postgresql-dev libffi-dev libmagic libcurl python3-dev openssl-dev curl-dev musl-dev rust cargo git \
  && python -m pip install --upgrade pip \
  && python -m pip install wheel \
  && pip install "Cython<3.0" \
  && pip install "pyyaml==6.0.0" --no-build-isolation \
  && pip install --upgrade setuptools==65.5.1

COPY --chown=vanotify requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

VOLUME /app

USER vanotify
CMD ["./scripts/run_app.sh"]
