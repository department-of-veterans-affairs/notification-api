import base64
from contextlib import suppress
from dataclasses import dataclass
from logging import Logger
from monotonic import monotonic
from urllib.parse import parse_qs

from sqlalchemy import update, text
from twilio.rest import Client
from twilio.rest.api.v2010.account.message import MessageInstance
from twilio.base.exceptions import TwilioRestException

from app import db
from app.clients.sms import SmsClient, SmsStatusRecord

from app.exceptions import InvalidProviderException


TWILIO_RESPONSE_MAP = {
    'accepted': 'created',
    'queued': 'sending',
    'sending': 'sending',
    'sent': 'sent',
    'delivered': 'delivered',
    'undelivered': 'permanent-failure',
    'failed': 'technical-failure',
    'received': 'received',
}


def get_twilio_responses(status):
    return TWILIO_RESPONSE_MAP[status]


@dataclass
class TwilioStatus:
    code: int | None
    status: str
    status_reason: str | None


class TwilioSMSClient(SmsClient):
    def __init__(
        self,
        account_sid=None,
        auth_token=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        # Twilio docs at.
        # https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides
        self.callback_url = None
        self._callback_connection_timeout = 3000  # milliseconds, 10 seconds
        self._callback_read_timeout = 1500  # milliseconds, 15 seconds
        self._callback_retry_count = 5
        self._callback_retry_policy = 'all'
        self._callback_notify_url_host = None
        self.logger: Logger = None
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._client = Client(account_sid, auth_token)

        # Importing inline to resolve a circular import error when importing
        # at the top of the file
        from app.models import (
            NOTIFICATION_DELIVERED,
            NOTIFICATION_TECHNICAL_FAILURE,
            NOTIFICATION_SENDING,
            NOTIFICATION_PERMANENT_FAILURE,
            NOTIFICATION_SENT,
        )

        self.twilio_error_code_map = {
            '30001': TwilioStatus(30001, NOTIFICATION_TECHNICAL_FAILURE, 'Queue overflow'),
            '30002': TwilioStatus(30002, NOTIFICATION_PERMANENT_FAILURE, 'Account suspended'),
            '30003': TwilioStatus(30003, NOTIFICATION_PERMANENT_FAILURE, 'Unreachable destination handset'),
            '30004': TwilioStatus(30004, NOTIFICATION_PERMANENT_FAILURE, 'Message blocked'),
            '30005': TwilioStatus(30005, NOTIFICATION_PERMANENT_FAILURE, 'Unknown destination handset'),
            '30006': TwilioStatus(30006, NOTIFICATION_PERMANENT_FAILURE, 'Landline or unreachable carrier'),
            '30007': TwilioStatus(30007, NOTIFICATION_PERMANENT_FAILURE, 'Message filtered'),
            '30008': TwilioStatus(30008, NOTIFICATION_TECHNICAL_FAILURE, 'Unknown error'),
            '30009': TwilioStatus(30009, NOTIFICATION_TECHNICAL_FAILURE, 'Missing inbound segment'),
            '30010': TwilioStatus(30010, NOTIFICATION_TECHNICAL_FAILURE, 'Message price exceeds max price'),
            '30034': TwilioStatus(30034, NOTIFICATION_PERMANENT_FAILURE, 'Used an unregistered 10DLC Number'),
        }

        self.twilio_notify_status_map = {
            'accepted': TwilioStatus(None, NOTIFICATION_SENDING, None),
            'scheduled': TwilioStatus(None, NOTIFICATION_SENDING, None),
            'queued': TwilioStatus(None, NOTIFICATION_SENDING, None),
            'sending': TwilioStatus(None, NOTIFICATION_SENDING, None),
            'sent': TwilioStatus(None, NOTIFICATION_SENT, None),
            'delivered': TwilioStatus(None, NOTIFICATION_DELIVERED, None),
            'undelivered': TwilioStatus(None, NOTIFICATION_PERMANENT_FAILURE, 'Unable to deliver'),
            'failed': TwilioStatus(None, NOTIFICATION_TECHNICAL_FAILURE, 'Technical error'),
            'canceled': TwilioStatus(None, NOTIFICATION_TECHNICAL_FAILURE, 'Notification cancelled'),
        }

    def init_app(
        self,
        logger,
        callback_notify_url_host,
        environment,
        *args,
        **kwargs,
    ):
        self.logger = logger
        self._callback_notify_url_host = callback_notify_url_host

        prefix = 'dev-'
        if environment == 'staging':
            prefix = 'staging-'
        elif environment == 'performance':
            prefix = 'sandbox-'
        elif environment == 'production':
            prefix = ''

        self.callback_url = (
            f'https://{prefix}api.va.gov/vanotify/sms/deliverystatus'
            f'#ct={self._callback_connection_timeout}'
            f'&rc={self._callback_retry_count}'
            f'&rt={self._callback_read_timeout}'
            f'&rp={self._callback_retry_policy}'
        )

    @property
    def name(self):
        return 'twilio'

    def get_name(self):
        return self.name

    def get_twilio_message(self, message_sid: str) -> MessageInstance | None:
        message = None
        with suppress(TwilioRestException):
            message = self._client.messages(message_sid).fetch()
        return message

    def send_sms(
        self,
        to,
        content,
        reference,
        **kwargs,
    ) -> str:
        """
        Twilio supports sending messages with a sender phone number
        or messaging_service_sid.

        Return: a string containing the Twilio message.sid
        """

        start_time = monotonic()

        try:
            # Importing inline to resolve a circular import error when
            # importing at the top of the file
            from app.dao.service_sms_sender_dao import (
                dao_get_service_sms_sender_by_service_id_and_number,
                dao_get_service_sms_sender_by_id,
            )

            from_number = None
            messaging_service_sid = None
            sms_sender_id = kwargs.get('sms_sender_id')

            # If sms_sender_id is available, get the specified sender.
            # Otherwise, get the first sender for the service.
            if sms_sender_id is not None:
                # This is an instance of ServiceSmsSender or None.
                service_sms_sender = dao_get_service_sms_sender_by_id(
                    service_id=kwargs.get('service_id'),
                    service_sms_sender_id=sms_sender_id,
                )
            else:
                # This is an instance of ServiceSmsSender or None.
                service_sms_sender = dao_get_service_sms_sender_by_service_id_and_number(
                    service_id=kwargs.get('service_id'), number=kwargs.get('sender')
                )

            if service_sms_sender is not None:
                from_number = service_sms_sender.sms_sender

                if service_sms_sender.sms_sender_specifics is not None:
                    messaging_service_sid = service_sms_sender.sms_sender_specifics.get('messaging_service_sid')

                    self.logger.info('Twilio sender has sms_sender_specifics')

            if messaging_service_sid is None:
                # Make a request using a sender phone number.
                message = self._client.messages.create(
                    to=to,
                    from_=from_number,
                    body=content,
                    status_callback=self.callback_url,
                )

                self.logger.info('Twilio message created using number: %s', from_number)
            else:
                # Make a request using the messaging service sid.
                #    https://www.twilio.com/docs/messaging/services
                message = self._client.messages.create(
                    to=to,
                    messaging_service_sid=messaging_service_sid,
                    body=content,
                    status_callback=self.callback_url,
                )

                self.logger.info('Twilio message created using messaging_service_sid: %s', messaging_service_sid)

            self.logger.info('Twilio send SMS request for %s succeeded: %s', reference, message.sid)

            return message.sid
        except TwilioRestException as e:
            if e.status == 400 and 'phone number' in e.msg:
                self.logger.exception('Twilio send SMS request for %s failed', reference)
                raise InvalidProviderException from e
            else:
                raise
        except:
            self.logger.exception('Twilio send SMS request for %s failed', reference)
            raise
        finally:
            elapsed_time = monotonic() - start_time
            self.logger.info(
                'Twilio send SMS request for %s  finished in %f',
                reference,
                elapsed_time,
            )

    def translate_delivery_status(
        self,
        twilio_delivery_status_message: str,
    ) -> SmsStatusRecord:
        """
        Parses the base64 encoded delivery status message from Twilio and returns a dictionary.
        The dictionary contains the following keys:
        - record_status: the convereted twilio to notification platform status
        - reference: the message id of the twilio message
        - payload: the original payload from twilio
        https://github.com/department-of-veterans-affairs/vanotify-team/blob/main/Engineering/SPIKES/SMS-Delivery-Status.md#twilio-implementation-of-delivery-statuses
        """
        self.logger.info('Translating Twilio delivery status')
        self.logger.debug(twilio_delivery_status_message)

        decoded_msg, parsed_dict = self._parse_twilio_message(twilio_delivery_status_message)

        message_sid = parsed_dict['MessageSid'][0]
        twilio_delivery_status = parsed_dict['MessageStatus'][0]
        error_code = parsed_dict.get('ErrorCode', [])

        status, status_reason = self._evaluate_status(message_sid, twilio_delivery_status, error_code)

        status = SmsStatusRecord(
            decoded_msg,
            message_sid,
            status,
            status_reason,
        )

        self.logger.debug('Twilio delivery status translation: %s', status)

        return status

    def update_notification_status(self, message_sid: str) -> None:
        from app.dao.notifications_dao import dao_update_notifications_by_reference

        self.logger.info('Updating notification status for message: %s', message_sid)

        message = self.get_twilio_message(message_sid)
        self.logger.debug('Twilio message: %s', message)

        status, status_reason = self._evaluate_status(message_sid, message.status, [])
        update_dict = {
            'status': status,
            'status_reason': status_reason,
        }
        dao_update_notifications_by_reference(
            [
                message_sid,
            ],
            update_dict,
        )

    def _parse_twilio_message(self, twilio_delivery_status_message: MessageInstance) -> tuple[str, dict]:
        if not twilio_delivery_status_message:
            raise ValueError('Twilio delivery status message is empty')

        decoded_msg = base64.b64decode(twilio_delivery_status_message).decode()
        parsed_dict = parse_qs(decoded_msg)

        return decoded_msg, parsed_dict

    def _evaluate_status(self, message_sid: str, twilio_delivery_status: str, error_codes: list) -> tuple[str, str]:
        if twilio_delivery_status not in self.twilio_notify_status_map:
            value_error = f'Invalid Twilio delivery status:  {twilio_delivery_status}'
            raise ValueError(value_error)

        if error_codes and (twilio_delivery_status == 'failed' or twilio_delivery_status == 'undelivered'):
            error_code = error_codes[0]

            if error_code in self.twilio_error_code_map:
                notify_delivery_status: TwilioStatus = self.twilio_error_code_map[error_code]
            else:
                self.logger.warning(
                    'Unaccounted for Twilio Error code: %s with message sid: %s', error_code, message_sid
                )
                notify_delivery_status: TwilioStatus = self.twilio_notify_status_map[twilio_delivery_status]
        else:
            # Logic not being changed, just want to log this for now
            if error_codes:
                self.logger.warning(
                    'Error code: %s existed but status for message: %s was not failed nor undelivered',
                    error_code,
                    message_sid,
                )
            notify_delivery_status: TwilioStatus = self.twilio_notify_status_map[twilio_delivery_status]

        return notify_delivery_status.status, notify_delivery_status.status_reason
