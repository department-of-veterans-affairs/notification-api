from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from http.client import responses
from typing import TYPE_CHECKING, Optional


import iso8601
import requests

from app.feature_flags import FeatureFlag, is_feature_enabled
from app.va.identifier import OIDS, IdentifierType, transform_to_fhir_format
from app.va.va_profile import (
    NoContactInfoException,
    VAProfileNonRetryableException,
    VAProfileRetryableException,
)
from app.va.va_profile.exceptions import (
    CommunicationItemNotFoundException,
    InvalidPhoneNumberException,
    VAProfileIDNotFoundException,
)

if TYPE_CHECKING:
    from app.models import RecipientIdentifier, Notification
    from va_profile_types import CommunicationPermissions, ContactInformation, Profile, Telephone


VA_NOTIFY_TO_VA_PROFILE_NOTIFICATION_TYPES = {
    'email': 'Email',
    'sms': 'Text',
}

VALID_PHONE_TYPES_FOR_SMS_DELIVERY = [
    0,  # "MOBILE"
    2,  # "VOIP"
    5,  # "PREPAID"
]


class CommunicationChannel(Enum):
    EMAIL = ('Email', 2)
    TEXT = ('Text', 1)

    def __new__(cls, value, id):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.id = id
        return obj


class PhoneNumberType(Enum):
    MOBILE = 'MOBILE'
    HOME = 'HOME'
    WORK = 'WORK'
    FAX = 'FAX'
    TEMPORARY = 'TEMPORARY'

    @staticmethod
    def valid_type_values() -> list[str]:
        return [PhoneNumberType.MOBILE.value, PhoneNumberType.HOME.value]


@dataclass
class VAProfileResult:
    recipient: str
    communication_allowed: bool
    permission_message: str | None


class VAProfileClient:
    SUCCESS_STATUS = 'COMPLETED_SUCCESS'
    EMAIL_BIO_TYPE = 'emails'
    PHONE_BIO_TYPE = 'telephones'
    TX_AUDIT_ID = 'txAuditId'

    def init_app(
        self,
        logger,
        va_profile_url,
        ssl_cert_path,
        ssl_key_path,
        va_profile_token,
        statsd_client,
    ):
        self.logger = logger
        self.va_profile_url = va_profile_url
        self.ssl_cert_path = ssl_cert_path
        self.ssl_key_path = ssl_key_path
        self.va_profile_token = va_profile_token
        self.statsd_client = statsd_client

    def get_profile(self, va_profile_id: RecipientIdentifier) -> Profile:
        """
        Retrieve the profile information for a given VA profile ID using the v3 API endpoint.

        Args:
            va_profile_id (RecipientIdentifier): The VA profile ID to retrieve the profile for.

        Returns:
            Profile: The profile information retrieved from the VA Profile service.
        """
        recipient_id = transform_to_fhir_format(va_profile_id)
        oid = OIDS.get(IdentifierType.VA_PROFILE_ID)
        url = f'{self.va_profile_url}/profile-service/profile/v3/{oid}/{recipient_id}'
        data = {'bios': [{'bioPath': 'contactInformation'}, {'bioPath': 'communicationPermissions'}]}

        try:
            response = requests.post(url, json=data, cert=(self.ssl_cert_path, self.ssl_key_path), timeout=(3.05, 1))
            response.raise_for_status()
        except (requests.HTTPError, requests.RequestException, requests.Timeout) as e:
            self._handle_exceptions(va_profile_id.id_value, e)

        response_json: dict = response.json()
        return response_json.get('profile', {})

    def get_telephone(self, va_profile_id: RecipientIdentifier) -> str:
        """
        Retrieve the telephone number from the profile information for a given VA profile ID.

        Args:
            va_profile_id (RecipientIdentifier): The VA profile ID to retrieve the telephone number for.

        Returns:
            str: The telephone number retrieved from the VA Profile service.
        """
        contact_info: ContactInformation = self.get_profile(va_profile_id).get('contactInformation', {})
        self.logger.debug('V3 Profile - Retrieved ContactInformation: %s', contact_info)

        telephones: list[Telephone] = contact_info.get(self.PHONE_BIO_TYPE, [])
        sorted_telephones = sorted(
            [phone for phone in telephones if phone['phoneType'] == PhoneNumberType.MOBILE.value],
            key=lambda phone: iso8601.parse_date(phone['createDate']),
            reverse=True,
        )
        if sorted_telephones:
            if (
                sorted_telephones[0].get('countryCode')
                and sorted_telephones[0].get('areaCode')
                and sorted_telephones[0].get('phoneNumber')
            ):
                self.statsd_client.incr('clients.va-profile.get-telephone.success')
                # https://en.wikipedia.org/wiki/E.164 format
                return f"+{sorted_telephones[0]['countryCode']}{sorted_telephones[0]['areaCode']}{sorted_telephones[0]['phoneNumber']}"

        self.statsd_client.incr('clients.va-profile.get-telephone.failure')
        self._raise_no_contact_info_exception(self.PHONE_BIO_TYPE, va_profile_id, contact_info.get(self.TX_AUDIT_ID))

    def get_email(self, va_profile_id: RecipientIdentifier) -> str:
        """
        Retrieve the email address from the profile information for a given VA profile ID.

        Args:
            va_profile_id (RecipientIdentifier): The VA profile ID to retrieve the email address for.

        Returns:
            str: The email address retrieved from the VA Profile service.
        """
        contact_info: ContactInformation = self.get_profile(va_profile_id).get('contactInformation', {})
        sorted_emails = sorted(
            contact_info.get(self.EMAIL_BIO_TYPE, []),
            key=lambda email: iso8601.parse_date(email['createDate']),
            reverse=True,
        )
        if sorted_emails:
            self.statsd_client.incr('clients.va-profile.get-email.success')
            return sorted_emails[0].get('emailAddressText')

        self.statsd_client.incr('clients.va-profile.get-email.failure')
        self._raise_no_contact_info_exception(self.EMAIL_BIO_TYPE, va_profile_id, contact_info.get(self.TX_AUDIT_ID))

    def has_valid_mobile_telephone_classification(self, telephone: Telephone, contact_info: ContactInformation) -> bool:
        """
        Args:
          telephone (Telephone): telephone entry from ContactInformation object retrieved from Vet360 API endpoint

        Returns:
          bool - if AWS-classified telephone is a valid sms recipient (if nonexistent, return True)

        Raises:
          InvalidPhoneNumberException - if AWS-classified telephone is not a valid sms recipient
        """
        classification = telephone.get('classification', {})
        classification_code = classification.get('classificationCode', None)
        if classification_code is None:
            # fall back, if no phone number classification is present
            self.logger.debug(
                'V3 Profile -- No telephone classification present, assuming the number is a valid SMS recipient (VA Profile ID: %s)',
                telephone['vaProfileId'],
            )
            return True

        if classification_code not in VALID_PHONE_TYPES_FOR_SMS_DELIVERY:
            self.logger.debug(
                'V3 Profile -- Phone classification code of %s is not a valid SMS recipient (VA Profile ID: %s)',
                classification_code,
                telephone['vaProfileId'],
            )
            self._raise_invalid_phone_number_exception(contact_info)

        self.logger.debug(
            'V3 Profile -- Phone classification code of %s is a valid SMS recipient (VA Profile ID: %s)',
            classification_code,
            telephone['vaProfileId'],
        )
        return True

    def get_mobile_telephone_from_contact_info(self, contact_info: ContactInformation) -> Optional[str]:
        """
        Find the most recently created mobile phone number from a veteran's Vet360 contact information

        Args:
            contact_info (ContactInformation):  Contact Information object retrieved from Vet360 API endpoint

        Returns:
            string representation of the most recently created mobile phone number, or None
        """
        telephones: list[Telephone] = contact_info.get(self.PHONE_BIO_TYPE, [])

        sorted_telephones = sorted(
            [phone for phone in telephones if phone['phoneType'] == PhoneNumberType.MOBILE.value],
            key=lambda phone: iso8601.parse_date(phone['createDate']),
            reverse=True,
        )

        if sorted_telephones:
            is_mobile = True
            if is_feature_enabled(FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS):
                self.logger.debug(
                    'V3 Profile -- VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS enabled.  Checking telephone classification info.'
                )
                is_mobile = self.has_valid_mobile_telephone_classification(sorted_telephones[0], contact_info)
            else:
                self.logger.debug(
                    'V3 Profile -- VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS is not enabled.  Will not check classification info.'
                )
            if (
                is_mobile
                and sorted_telephones[0].get('countryCode')
                and sorted_telephones[0].get('areaCode')
                and sorted_telephones[0].get('phoneNumber')
            ):
                self.statsd_client.incr('clients.va-profile.get-telephone.success')
                return f"+{sorted_telephones[0]['countryCode']}{sorted_telephones[0]['areaCode']}{sorted_telephones[0]['phoneNumber']}"

    def get_telephone_with_permission(
        self,
        va_profile_id: RecipientIdentifier,
        notification: Notification,
    ) -> VAProfileResult:
        """
        Retrieve the telephone number from the profile information for a given VA profile ID.

        Args:
            va_profile_id (RecipientIdentifier): The VA profile ID to retrieve the telephone number for.
            notification (Notification): Notification object which contains needed default_send and communication_item details

        Returns:
            VAProfileResults: The result data.
            Property recipient is the telephone number retrieved from the VA Profile service.
            Property communication_allowed is true when VA Profile service indicates that the recipient has allowed communication.
            Property permission_message may contain an error message if the permission check encountered an exception.
        """
        profile: Profile = self.get_profile(va_profile_id)
        communication_allowed = notification.default_send
        permission_message = None
        try:
            communication_allowed = self.get_is_communication_allowed_from_profile(
                profile, notification, CommunicationChannel.TEXT
            )
        except CommunicationItemNotFoundException:
            self.logger.info('Communication item for recipient %s not found', va_profile_id)
            permission_message = 'No recipient opt-in found for explicit preference'

        contact_info: ContactInformation = profile.get('contactInformation', {})

        telephone = self.get_mobile_telephone_from_contact_info(contact_info)
        if not telephone:
            self.statsd_client.incr('clients.va-profile.get-telephone.failure')
            self._raise_no_contact_info_exception(
                self.PHONE_BIO_TYPE, va_profile_id, contact_info.get(self.TX_AUDIT_ID)
            )

        return VAProfileResult(telephone, communication_allowed, permission_message)

    def get_email_with_permission(
        self,
        va_profile_id: RecipientIdentifier,
        notification: Notification,
    ) -> VAProfileResult:
        """
        Retrieve the email address from the profile information for a given VA profile ID.

        Args:
            va_profile_id (RecipientIdentifier): The VA profile ID to retrieve the email address for.
            notification (Notification): Notification object which contains needed default_send and communication_item details

        Returns:
            VAProfileResults: The result data.
            Property recipient is the telephone number retrieved from the VA Profile service.
            Property communication_allowed is true when VA Profile service indicates that the recipient has allowed communication.
            Property permission_message may contain an error message if the permission check encountered an exception.
        """
        profile = self.get_profile(va_profile_id)
        communication_allowed = notification.default_send
        permission_message = None

        try:
            communication_allowed = self.get_is_communication_allowed_from_profile(
                profile, notification, CommunicationChannel.EMAIL
            )
        except CommunicationItemNotFoundException:
            self.logger.info('Communication item for recipient %s not found', va_profile_id)
            permission_message = 'No recipient opt-in found for explicit preference'

        contact_info: ContactInformation = profile.get('contactInformation', {})
        sorted_emails = sorted(
            contact_info.get(self.EMAIL_BIO_TYPE, []),
            key=lambda email: iso8601.parse_date(email['createDate']),
            reverse=True,
        )
        if sorted_emails:
            self.statsd_client.incr('clients.va-profile.get-email.success')
            email_result = sorted_emails[0].get('emailAddressText')
            return VAProfileResult(email_result, communication_allowed, permission_message)

        self.statsd_client.incr('clients.va-profile.get-email.failure')
        self._raise_no_contact_info_exception(self.EMAIL_BIO_TYPE, va_profile_id, contact_info.get(self.TX_AUDIT_ID))

    def get_is_communication_allowed(
        self,
        recipient_id: RecipientIdentifier,
        communication_item_id: str,
        notification_id: str,
        notification_type: str,
        default_send: bool,
    ) -> bool:
        """
        Determine if communication is allowed for a given recipient, communication item, and notification type.

        Args:
            recipient_id (RecipientIdentifier): The recipient's VA profile ID.
            communication_item_id (str): The ID of the communication item.
            notification_id (str): The ID of the notification.
            notification_type (str): The type of the notification.

        Returns:
            bool: True if communication is allowed, False otherwise.

        Raises:
            CommunicationItemNotFoundException: If no communication permissions are found for the given parameters.
        """

        communication_permissions: CommunicationPermissions = self.get_profile(recipient_id).get(
            'communicationPermissions', {}
        )
        communication_channel = CommunicationChannel(VA_NOTIFY_TO_VA_PROFILE_NOTIFICATION_TYPES[notification_type])
        for perm in communication_permissions:
            if (
                perm['communicationChannelId'] == communication_channel.id
                and perm['communicationItemId'] == communication_item_id
            ):
                self.statsd_client.incr('clients.va-profile.get-communication-item-permission.success')
                # if default send is true and allowed is false, return false
                # if default send is true and allowed is true, return true
                # if default send is false, default to what it finds
                permission: bool | None = perm['allowed']
                if permission is not None:
                    return perm['allowed']
                else:
                    return default_send

        self.logger.debug(
            'V3 Profile -- Recipient %s did not have permission for communication item %s and channel %s for notification %s',
            recipient_id,
            communication_item_id,
            notification_type,
            notification_id,
        )

        # TODO 893 - use default communication item settings when that has been implemented
        self.statsd_client.incr('clients.va-profile.get-communication-item-permission.no-permissions')
        raise CommunicationItemNotFoundException

    def get_is_communication_allowed_from_profile(
        self,
        profile: Profile,
        notification: Notification,
        communication_channel: CommunicationChannel,
    ) -> bool:
        """
        Determine if communication is allowed for a given recipient, communication item, and notification type.

        Argsj
            profile (Profile): The recipient's profile.
            notification (Notification): Notification object
            communication_channel (CommunicationChannel): Communication channel to send the notification

        Returns:
            bool: True if communication is allowed, False otherwise.

        Raises:
            CommunicationItemNotFoundException: If no communication permissions are found for the given parameters.
        """

        communication_permissions: CommunicationPermissions = profile.get('communicationPermissions', {})
        for perm in communication_permissions:
            if (
                perm['communicationChannelId'] == communication_channel.id
                and perm['communicationItemId'] == notification.va_profile_item_id
            ):
                self.statsd_client.incr('clients.va-profile.get-communication-item-permission.success')
                # if default send is true and allowed is false, return false
                # if default send is true and allowed is true, return true
                # if default send is false, default to what it finds
                permission: bool | None = perm['allowed']
                if permission is not None:
                    return perm['allowed']
                else:
                    return notification.default_send

        self.logger.debug(
            'V3 Profile -- did not have permission for communication item %s and channel %s',
            notification.va_profile_item_id,
            communication_channel.value,
        )

        # TODO 893 - use default communication item settings when that has been implemented
        self.statsd_client.incr('clients.va-profile.get-communication-item-permission.no-permissions')
        raise CommunicationItemNotFoundException

    def _handle_exceptions(self, va_profile_id_value: str, error: Exception):
        """
        Handle exceptions that occur during requests to the VA Profile service.

        Args:
            va_profile_id_value (str): The VA profile ID value associated with the request.
            error (Exception): The exception that was raised during the request.

        Raises:
            VAProfileRetryableException: If the error is a retryable HTTP error or a RequestException.
            VAProfileIDNotFoundException: If the error is a 404 HTTP error.
            VAProfileNonRetryableException: If the error is a non-retryable HTTP error.
            requests.Timeout: If the error is a Timeout exception.
        """
        if isinstance(error, requests.HTTPError):
            self.logger.warning(
                'HTTPError raised making request to VA Profile for VA Profile ID: %s', va_profile_id_value
            )
            self.statsd_client.incr(f'clients.va-profile.error.{error.response.status_code}')

            failure_reason = (
                f'Received {responses[error.response.status_code]} HTTP error ({error.response.status_code}) while making a '
                'request to obtain info from VA Profile'
            )

            if error.response.status_code in [429, 500, 502, 503, 504]:
                exception = VAProfileRetryableException(str(error))
                exception.failure_reason = failure_reason

                raise exception from error
            elif error.response.status_code == 404:
                exception = VAProfileIDNotFoundException(str(error))

                raise exception from error
            else:
                exception = VAProfileNonRetryableException(str(error))
                exception.failure_reason = failure_reason

                raise exception from error

        elif isinstance(error, requests.RequestException):
            self.statsd_client.incr('clients.va-profile.error.request_exception')
            failure_message = 'VA Profile returned RequestException while querying for VA Profile ID'

            if isinstance(error, requests.Timeout):
                failure_message = f'VA Profile request timed out for VA Profile ID {va_profile_id_value}.'

            exception = VAProfileRetryableException(failure_message)
            exception.failure_reason = failure_message

            raise exception from error

    def _raise_no_contact_info_exception(
        self,
        bio_type: str,
        va_profile_id: str,
        tx_audit_id: str,
    ):
        self.statsd_client.incr(f'clients.va-profile.get-{bio_type}.no-{bio_type}')
        raise NoContactInfoException(
            f'No {bio_type} in response for VA Profile ID {va_profile_id} ' f'with AuditId {tx_audit_id}'
        )

    def _raise_invalid_phone_number_exception(self, contact_info: ContactInformation):
        self.statsd_client.incr(f'clients.va-profile.get-{self.PHONE_BIO_TYPE}.no-{self.PHONE_BIO_TYPE}')
        raise InvalidPhoneNumberException(
            f'No valid {self.PHONE_BIO_TYPE} in response for VA Profile ID {contact_info.get("vaProfileId")} '
            f'with AuditId {contact_info.get("txAuditId")}'
        )

    def send_va_profile_email_status(self, notification_data: dict) -> None:
        """
        This method sends notification status data to VA Profile. This is part of our integration to help VA Profile
        provide better service by letting them know which emails are good, and which ones result in bounces.

        :param notification_data: the data to include with the POST request to VA Profile

        Raises:
            requests.Timeout: if the request to VA Profile times out
            RequestException: if something unexpected happens when sending the request
        """

        headers = {'Authorization': f'Bearer {self.va_profile_token}'}
        url = f'{self.va_profile_url}/contact-information-vanotify/notify/status'

        self.logger.debug(
            'Sending email status to VA Profile with url: %s | notification: %s', url, notification_data.get('id')
        )

        # make POST request to VA Profile endpoint for notification statuses
        # raise errors if they occur, they will be handled by the calling function
        try:
            response = requests.post(url, json=notification_data, headers=headers, timeout=(3.05, 1))
        except requests.Timeout:
            self.logger.exception(
                'Request timeout attempting to send email status to VA Profile for notification %s | retrying...',
                notification_data.get('id'),
            )
            raise
        except requests.RequestException:
            self.logger.exception(
                'Unexpected request exception.  E-mail status NOT sent to VA Profile for notification %s.',
                notification_data.get('id'),
            )
            raise

        self.logger.info(
            'VA Profile response when receiving status of notification %s | status code: %s | json: %s',
            notification_data.get('id'),
            response.status_code,
            response.json(),
        )
