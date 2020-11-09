import pytest

from app.clients.email import EmailClient


class TestEmailClient(EmailClient):

    def init_app(self, name):
        self.name = name

    def get_name(self):
        return self.name

    def send_email(self, *args, **kwargs):
        # do nothing as it is for testing
        pass


@pytest.fixture(scope='function')
def delivery_client_with_space_in_name():
    email_client = TestEmailClient()
    email_client.init_app('name with space')
    return email_client


@pytest.fixture(scope='function')
def delivery_client_with_name():
    email_client = TestEmailClient()
    email_client.init_app('testdeliveryclient')
    return email_client
