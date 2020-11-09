import pytest

from app.clients.email import EmailClient


class DeliveryClientWithSpaceInName(EmailClient):

    def init_app(self):
        self.name = 'name with space'

    def get_name(self):
        return self.name

    def send_email(self, *args, **kwargs):
        # do nothing as it is for testing
        pass


@pytest.fixture(scope='function')
def delivery_client_with_space_in_name():
    email_client = DeliveryClientWithSpaceInName()
    email_client.init_app()
    return email_client
