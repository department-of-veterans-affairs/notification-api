import requests
import iso8601
from time import monotonic

from app.va.va_profile import (
    NoContactInfoException,
    VAProfileNonRetryableException,
    VAProfileRetryableException
)


class VAProfileClient:

    SUCCESS_STATUS = 'COMPLETED_SUCCESS'

    def init_app(self, logger, va_profile_url, ssl_cert_path, ssl_key_path, statsd_client):
        self.logger = logger
        self.va_profile_url = va_profile_url
        self.ssl_cert_path = ssl_cert_path
        self.ssl_key_path = ssl_key_path
        self.statsd_client = statsd_client

    def get_email(self, va_profile_id):
        self.logger.info(f"Querying VA Profile with ID {va_profile_id}")
        response = self._make_request(va_profile_id, 'emails')

        try:
            most_recently_created_bio = self._get_most_recently_created_bio(response)
            self.statsd_client.incr("clients.va-profile.get-email.success")
            return most_recently_created_bio['emailAddressText']
        except KeyError as e:
            self.statsd_client.incr("clients.va-profile.get-email.error")
            raise NoContactInfoException(f"No email in response for VA Profile ID {va_profile_id}") from e

    def get_telephone(self, va_profile_id):
        self.logger.info(f"Querying VA Profile with ID {va_profile_id}")
        response = self._make_request(va_profile_id, 'telephones')

        try:
            most_recently_created_bio = self._get_most_recently_created_bio(response)
            self.statsd_client.incr("clients.va-profile.get-telephone.success")
            return most_recently_created_bio
        except KeyError as e:
            self.statsd_client.incr("clients.va-profile.get-telephone.error")
            raise NoContactInfoException(f"No telephone in response for VA Profile ID {va_profile_id}") from e

    def _make_request(self, va_profile_id, bio_type):
        start_time = monotonic()
        try:
            response = requests.get(
                f"{self.va_profile_url}/contact-information-hub/cuf/contact-information/v1/{va_profile_id}/{bio_type}",
                cert=(self.ssl_cert_path, self.ssl_key_path)
            )
            response.raise_for_status()

        except requests.HTTPError as e:
            self.logger.exception(e)
            self.statsd_client.incr(f"clients.va-profile.error.{e.response.status_code}")
            if e.response.status_code in [429, 500, 502, 503, 504]:
                raise VAProfileRetryableException(str(e)) from e
            else:
                raise VAProfileNonRetryableException(str(e)) from e

        except requests.RequestException as e:
            self.statsd_client.incr(f"clients.va-profile.error.request_exception")
            raise VAProfileRetryableException(f"VA Profile returned {str(e)} while querying for VA Profile ID") from e

        else:
            response_status = response.json()['status']
            if response_status != self.SUCCESS_STATUS:
                self.statsd_client.incr(f"clients.va-profile.error.{response_status}")
                raise VAProfileNonRetryableException(
                    f"Response status was {response_status} for VA Profile ID {va_profile_id}"
                )

            self.statsd_client.incr("clients.va-profile.success")
            return response

        finally:
            elapsed_time = monotonic() - start_time
            self.statsd_client.timing("clients.va-profile.request-time", elapsed_time)

    def _get_most_recently_created_bio(self, response):
        sorted_bios = sorted(
            response.json()['bios'],
            key=lambda bio: iso8601.parse_date(bio['createDate']),
            reverse=True
        )
        return sorted_bios[0]
