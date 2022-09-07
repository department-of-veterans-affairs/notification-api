from monotonic import monotonic
from app.clients.sms import SmsClient
from twilio.rest import Client

twilio_response_map = {
    'accepted': 'created',
    'queued': 'sending',
    'sending': 'sending',
    'sent': 'sent',
    'delivered': 'delivered',
    'undelivered': 'permanent-failure',
    'failed': 'technical-failure',
    'received': 'received'
}


def get_twilio_responses(status):
    return twilio_response_map[status]


class TwilioSMSClient(SmsClient):
    def __init__(self,
                 account_sid=None,
                 auth_token=None,
                 from_number=None,
                 *args, **kwargs):
        super(TwilioSMSClient, self).__init__(*args, **kwargs)
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._client = Client(account_sid, auth_token)

    def init_app(self, logger, callback_notify_url_host, *args, **kwargs):
        self.logger = logger
        self._callback_notify_url_host = callback_notify_url_host

    @property
    def name(self):
        return 'twilio'

    def get_name(self):
        return self.name

    def send_sms(self, to, content, reference, **kwargs):
        """
        Twilio supports sending messages with a sender phone number or message_service_sid.
        """

        # could potentially select from potential numbers like this
        # from_number = random.choice(self._client.incoming_phone_numbers.list()).phone_number

        start_time = monotonic()
        from_number = self._from_number
        callback_url = "{}/notifications/sms/twilio/{}".format(
            self._callback_notify_url_host, reference) if self._callback_notify_url_host else ""
        try:
            # Importing inline to resolve a circular import error when importing at the top of the file
            from app.dao.service_sms_sender_dao import dao_get_service_sms_sender_by_service_id_and_number
            messaging_service_sid = None

            # This is an instance of ServiceSmsSender or None.
            service_sms_sender = dao_get_service_sms_sender_by_service_id_and_number(
                kwargs.get("service_id"),
                kwargs.get("sender")
            )

            if service_sms_sender and service_sms_sender.sms_sender_specifics:
                messaging_service_sid = service_sms_sender.sms_sender_specifics.get("messaging_service_sid")

                self.logger.info(f"Twilio sender has sms_sender_specifics "
                                 "value: {service_sms_sender.sms_sender_specifics}")

            if messaging_service_sid is None:
                # Make a request using a sender phone number.
                message = self._client.messages.create(
                    to=to,
                    from_=from_number,
                    body=content,
                    status_callback=callback_url,
                )

                self.logger.info(f"Twilio message created using from_number")
            else:
                # Make a request using the message service sid.
                #    https://www.twilio.com/docs/messaging/services
                message = self._client.messages.create(
                    to=to,
                    messaging_service_sid=messaging_service_sid,
                    body=content,
                    status_callback=callback_url,
                )

                self.logger.info(f"Twilio message created using messaging_service_sid")

            self.logger.info("Twilio send SMS request for {} succeeded: {}".format(reference, message.sid))
        except Exception as e:
            self.logger.error("Twilio send SMS request for {} failed".format(reference))
            raise e
        finally:
            elapsed_time = monotonic() - start_time
            self.logger.info("Twilio send SMS request for {} finished in {}".format(reference, elapsed_time))
