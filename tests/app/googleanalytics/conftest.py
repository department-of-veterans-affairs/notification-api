import pytest


class TestEmailClient:

    def __init__(self, name):
        self.name = name

    def get_name(self):
        return self.name


@pytest.fixture(scope='function')
def delivery_client_with_space_in_name():
    email_client = TestEmailClient('name with space')
    return email_client


@pytest.fixture(scope='function')
def delivery_client_with_name():
    email_client = TestEmailClient('testdeliveryclient')
    return email_client
