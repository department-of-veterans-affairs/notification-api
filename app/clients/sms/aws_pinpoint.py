import boto3
import botocore
from flask import current_app
from time import monotonic
from app.clients.sms import SmsClient, SmsClientResponseException


class AwsPinpointException(SmsClientResponseException):
    pass


class AwsPinpointClient(SmsClient):
    """
    AwsSns pinpoint client
    """
    def __init__(self):
        self._name = 'pinpoint'

    def init_app(self, aws_region, origination_number, statsd_client, logger, *args, **kwargs):
        self._client = boto3.client('pinpoint', region_name=aws_region)
        self.aws_region = aws_region
        self.logger = logger,
        self.origination_number = origination_number
        self.statsd_client = statsd_client

    def get_name(self):
        return self._name

    def send_sms(self, to: str, content, reference, multi=True, sender=None) -> str:
        recipient_number = str(to)

        try:
            start_time = monotonic()

            message_request_payload = {
                "Addresses": {
                    recipient_number: {
                        "ChannelType": "SMS"
                    }
                },
                "MessageConfiguration": {
                    "SMSMessage": {
                        "Body": content,
                        "MessageType": "TRANSACTIONAL",
                        "OriginationNumber": self.origination_number
                    }
                }
            }

            response = self._client.send_messages(
                ApplicationId=self.get_application_id(),  # TODO: error handling?
                MessageRequest=message_request_payload
            )

        except (botocore.exceptions.ClientError, Exception) as e:
            self.statsd_client.incr("clients.sms.error")
            raise AwsPinpointException(str(e))
        else:
            elapsed_time = monotonic() - start_time
            self.logger.info(f"AWS Pinpoint SMS request finished in {elapsed_time}")
            self.statsd_client.timing("clients.sms.request-time", elapsed_time)
            self.statsd_client.incr("clients.sms.success")
            return response['MessageResponse']['Result'][recipient_number]['MessageId']

    def get_application_id(self) -> str:
        response = self._client.get_apps()
        all_apps = response['ApplicationsResponse']['Item']

        for app in all_apps:
            if app['Name'] == current_app.config['AWS_PINPOINT_APP_NAME']:
                return app['Id']
