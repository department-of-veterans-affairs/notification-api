import pytest


class TestEmailClient:

    def __init__(self, name):
        self.name = name

    def get_name(self):
        return self.name

    def send_email(self, *args, **kwargs):
        # do nothing as it is for testing
        pass


@pytest.fixture(scope='function')
def test_email_client():
    email_client = TestEmailClient('testdeliveryclient')
    return email_client
