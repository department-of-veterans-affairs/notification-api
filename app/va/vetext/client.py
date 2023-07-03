import requests
from logging import Logger
from typing import Dict
from typing_extensions import TypedDict
from time import monotonic
from requests.auth import HTTPBasicAuth
from notifications_utils.clients.statsd.statsd_client import StatsdClient
from . import VETextRetryableException, VETextNonRetryableException, VETextBadRequestException


class Credentials(TypedDict):
    username: str
    password: str


class VETextClient:
    STATSD_KEY = "clients.vetext"
    TIMEOUT = 3.05

    def init_app(self, url: str, credentials: Credentials, logger: Logger, statsd: StatsdClient):
        self.base_url = url
        self.auth = HTTPBasicAuth(**credentials)
        self.logger = logger
        self.statsd = statsd

    def send_push_notification(self, mobile_app: str, template_id: str, icn: str, personalization: Dict = None) -> None:
        formatted_personalization = None
        if personalization:
            formatted_personalization = {}
            for key, value in personalization.items():
                formatted_personalization[f'%{key.upper()}%'] = value

        payload = {
            "appSid": mobile_app,
            "icn": icn,
            "templateSid": template_id,
            "personalization": formatted_personalization
        }
        self.logger.info("VEText Payload information: %s", payload)

        try:
            start_time = monotonic()
            response = requests.post(
                f"{self.base_url}/mobile/push/send",
                auth=self.auth,
                json=payload,
                timeout=self.TIMEOUT
            )
            self.logger.info("VEText response: %s", response.json() if response.ok else response.status_code)
            response.raise_for_status()
        except requests.HTTPError as e:
            self.logger.exception(e)
            self.statsd.incr(f"{self.STATSD_KEY}.error.{e.response.status_code}")
            if e.response.status_code in [429, 500, 502, 503, 504]:
                raise VETextRetryableException from e
                # TODO: add retries?
            elif e.response.status_code == 400:
                self._decode_bad_request_response(e)
            else:
                raise VETextNonRetryableException from e
        except requests.RequestException as e:
            self.logger.exception(e)
            self.statsd.incr(f"{self.STATSD_KEY}.error.request_exception")
            raise VETextRetryableException from e
            # TODO: add retries?
        else:
            self.statsd.incr(f"{self.STATSD_KEY}.success")
        finally:
            elapsed_time = monotonic() - start_time
            self.statsd.timing(f"{self.STATSD_KEY}.request_time", elapsed_time)

    def send_push(self, mobile_app: str, template_id: str, icn: str,
                        personalization: Dict = None, bad_req: int = None):
        # Because we cannot avoid the circular import...
        from app import notify_celery
        @notify_celery.task(bind=True, name="deliver_push", max_retries=48, retry_backoff=True, retry_backoff_max=60,
                    retry_jitter=True, autoretry_for=(VETextRetryableException,))
        def _send_push(task, mobile_app: str, template_id: str, icn: str,
                        personalization: Dict, bad_req: int) -> None:
            self.logger.info("Processing PUSH request with celery task ID: %s", task.request.id)
            formatted_personalization = None
            if personalization:
                formatted_personalization = {}
                for key, value in personalization.items():
                    key = key.upper()
                    # Handle requests that already wrapped it in percents
                    if not (key.startswith('%') and key.endswith('%')):
                        key = f"%{key}%"
                    formatted_personalization[key] = value

            payload = {
                "appSid": mobile_app,
                "icn": icn,
                "templateSid": template_id,
                "personalization": formatted_personalization
            }
            self.logger.debug("PUSH provider payload information: %s", payload)

            start_time = monotonic()
            try:
                if bad_req is None:
                    # 2xx
                    url = 'https://eo4hb96m2wtmqu9.m.pipedream.net'
                elif bad_req == 400:
                    # Not retryable
                    url = 'https://eokgc9awtoefud8.m.pipedream.net'
                else:
                    # retryable
                    url = 'https://eocenmyt46mltug.m.pipedream.net'
                response = requests.post(
                    # f"{self.base_url}/mobile/push/send",
                    url,  # KWM pipedream
                    auth=self.auth,
                    json=payload,
                    timeout=self.TIMEOUT
                )
                self.logger.info("PUSH provider response: %s", response.json() if response.ok else response.status_code)
                response.raise_for_status()
            except requests.HTTPError as e:
                self.statsd.incr(f"{self.STATSD_KEY}.error.{e.response.status_code}")
                if e.response.status_code == 400:
                    self.logger.critical("PUSH provider unable to process request: %s for task ID: %s",
                                            payload, task.request.id)
                    self._decode_bad_request_response(e)
                else:
                    self.logger.error("PUSH provider returned an HTTPError: %s, retrying task ID: %s", e, task.request.id)
                    raise VETextRetryableException from e
            except requests.RequestException as e:
                self.logger.error("PUSH provider returned an RequestException: %s", e)
                self.statsd.incr(f"{self.STATSD_KEY}.error.request_exception")
                raise VETextRetryableException from e
            else:
                self.statsd.incr(f"{self.STATSD_KEY}.success")
            finally:
                elapsed_time = monotonic() - start_time
                self.statsd.timing(f"{self.STATSD_KEY}.request_time", elapsed_time)
        _send_push(mobile_app, template_id, icn, personalization, bad_req)


    def _decode_bad_request_response(self, http_exception):
        try:
            payload = http_exception.response.json()
        except Exception:
            message = http_exception.response.text
            raise VETextBadRequestException(message=message) from http_exception
        else:
            field = payload.get("idType")
            message = payload.get("error")
            raise VETextBadRequestException(field=field, message=message) from http_exception


