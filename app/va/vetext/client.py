from dataclasses import asdict
from logging import Logger
from time import monotonic
from typing_extensions import TypedDict

import requests
from requests.auth import HTTPBasicAuth
from notifications_utils.clients.statsd.statsd_client import StatsdClient

from app.celery.exceptions import NonRetryableException, RetryableException
from app.v2.dataclasses import V2PushPayload


class Credentials(TypedDict):
    username: str
    password: str


class VETextClient:
    STATSD_KEY = 'clients.vetext'
    TIMEOUT = 3.05

    def init_app(
        self,
        url: str,
        credentials: Credentials,
        logger: Logger,
        statsd: StatsdClient,
    ):
        self.base_url = url
        self.auth = HTTPBasicAuth(**credentials)
        self.logger = logger
        self.statsd = statsd

    @staticmethod
    def format_for_vetext(payload: V2PushPayload) -> V2PushPayload:
        if payload.personalisation:
            payload.personalisation = {f'%{k.upper()}%': v for k, v in payload.personalisation.items()}

        return payload

    def send_push_notification(
        self,
        payload: V2PushPayload,
    ) -> None:
        """Send the notification to VEText and handle any errors.

        Args:
            payload (V2PushPayload): The data to send to VEText
        """
        self.logger.debug('VEText Payload information 2172: %s', payload)
        start_time = monotonic()
        try:
            response = requests.post(
                f'{self.base_url}/mobile/push/send', auth=self.auth, json=asdict(payload), timeout=self.TIMEOUT
            )
            self.logger.info(
                'VEText response: %s for payload 2172: %s',
                response.json() if response.ok else response.status_code,
                asdict(payload),
            )
            self.logger.info('VEText response text 2172: %s', response.text)
            response.raise_for_status()
        except requests.exceptions.ReadTimeout:
            # Discussion with VEText: read timeouts are still processed, so no need to retry
            self.logger.info('ReadTimeout raised sending push notification - notification still processed')
            self.statsd.incr(f'{self.STATSD_KEY}.error.read_timeout')
        except requests.exceptions.ConnectTimeout as e:
            self.logger.warning('ConnectTimeout raised sending push notification - Retrying')
            self.statsd.incr(f'{self.STATSD_KEY}.error.connection_timeout')
            raise RetryableException from e
        except requests.HTTPError as e:
            self.statsd.incr(f'{self.STATSD_KEY}.error.{e.response.status_code}')
            if e.response.status_code in [429, 500, 502, 503, 504]:
                self.logger.warning('Retryable exception raised with status code 2172: %s', e.response.status_code)
                raise RetryableException from e
            elif e.response.status_code == 400:
                self._decode_bad_request_response(e)
            else:
                payload['icn'] = '<redacted>'
                self.logger.exception(
                    'Status: %s - Not retrying - payload: %s',
                    e.response.status_code,
                    payload,
                )
                raise NonRetryableException from e
        except requests.RequestException as e:
            payload['icn'] = '<redacted>'
            self.logger.exception(
                'Exception raised sending push notification. Not retrying - payload: %s',
                payload,
            )
            self.statsd.incr(f'{self.STATSD_KEY}.error.request_exception')
            raise NonRetryableException from e
        else:
            self.statsd.incr(f'{self.STATSD_KEY}.success')
        finally:
            elapsed_time = monotonic() - start_time
            self.statsd.timing(f'{self.STATSD_KEY}.request_time', elapsed_time)

    def _decode_bad_request_response(
        self,
        http_exception,
    ):
        """Parse the response and raise an exception as this is always an exception

        Args:
            http_exception (Exception): The exception raised

        Raises:
            NonRetryableException: Raised exception
        """
        try:
            payload = http_exception.response.json()
            field = payload.get('idType')
            message = payload.get('error')
            self.logger.warning('Bad response from VEText: %s with field: ', message, field)
            raise NonRetryableException from http_exception
        except Exception:
            message = http_exception.response.text
            self.logger.warning('Bad response from VEText: %s', message)
            raise NonRetryableException from http_exception
