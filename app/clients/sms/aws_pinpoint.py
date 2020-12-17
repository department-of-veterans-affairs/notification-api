import boto3
import botocore
from time import monotonic
from app.clients.sms import SmsClient, SmsClientResponseException


class AwsPinpointException(SmsClientResponseException):
    pass


class AwsPinpoint(SmsClient):
    """
    AwsSns sms client
    """
    def init_app(self, aws_region, statsd_client, logger, *args, **kwargs):
        self._client = boto3.client('pinpoint', region_name=aws_region)
        super(SmsClient, self).__init__(*args, **kwargs)
        self.logger = logger
        self.name = 'pinpoint'
        self.statsd_client = statsd_client

    def get_name(self):
        return self.name

    def send_sms(self, to, content, reference, multi=True, sender=None):
        try:
            start_time = monotonic()

            response = self._client.send_messages(
                ApplicationId='',  # do this with get_apps()?
                MessageRequest={
                    "Addresses": {
                        to: {"ChannelType": "SMS"}
                    },
                    "MessageConfiguration": {
                        "SMSMessage": {
                            "Body": content,
                            "MessageType": "TRANSACTIONAL",
                            "OriginationNumber": "+12515727927"  # get from config or param store
                        }
                    }
                }
            )

        except (botocore.exceptions.ClientError, Exception) as e:
            self.statsd_client.incr("clients.sms.error")
            raise AwsPinpointException(str(e))
        else:
            elapsed_time = monotonic() - start_time
            self.logger.info(f"AWS Pinpoint SMS request finished in {elapsed_time}")
            self.statsd_client.timing("clients.sms.request-time", elapsed_time)
            self.statsd_client.incr("clients.sms.success")
            return response['MessageId']  # figure out what this would be used for
