#! /usr/bin/env bash
set -e

if [ -z ${VANOTIFY_SSL_CERT_PATH+x} -o -z ${VANOTIFY_SSL_KEY_PATH+x} ]
then
  echo "bypassing VAProfile cert and key file generation"
else
  echo "Writing SSL certificate and key to files"
  ls -l /app/certs/
  echo "this is a test" > /app/certs/kwm.txt
  ls -l /app/certs
  echo "$VANOTIFY_SSL_CERT" > $VANOTIFY_SSL_CERT_PATH
  echo "$VANOTIFY_SSL_KEY" > $VANOTIFY_SSL_KEY_PATH
fi

exec "$@"