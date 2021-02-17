import pytest

from app.models import Notification, ProviderDetails
from app.notifications.notification_type import NotificationType
from app.provider_details.provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.provider_details.provider_service import ProviderService


class ExampleEmailStrategy(ProviderSelectionStrategyInterface):

    @staticmethod
    def get_label() -> str:
        return 'EXAMPLE_EMAIL_STRATEGY'

    @staticmethod
    def get_provider(notification: Notification) -> ProviderDetails:
        pass


class ExampleSmsStrategy(ProviderSelectionStrategyInterface):

    @staticmethod
    def get_label() -> str:
        return 'EXAMPLE_SMS_STRATEGY'

    @staticmethod
    def get_provider(notification: Notification) -> ProviderDetails:
        pass


def test_initialises_and_uses_example_strategy(mocker):
    provider_service = ProviderService()
    provider_service.init_app(
        email_provider_selection_strategy_label='EXAMPLE_EMAIL_STRATEGY',
        sms_provider_selection_strategy_label='EXAMPLE_SMS_STRATEGY'
    )
    assert provider_service.strategies[NotificationType.EMAIL] == ExampleEmailStrategy
    assert provider_service.strategies[NotificationType.SMS] == ExampleSmsStrategy

    mock_email_provider = mocker.Mock()
    mocker.patch.object(ExampleEmailStrategy, 'get_provider', return_value=mock_email_provider)

    mock_email_notification = mocker.Mock(notification_type=NotificationType.EMAIL)
    assert provider_service.get_provider(mock_email_notification) == mock_email_provider

    mock_sms_provider = mocker.Mock()
    mocker.patch.object(ExampleSmsStrategy, 'get_provider', return_value=mock_sms_provider)

    mock_sms_notification = mocker.Mock(notification_type=NotificationType.SMS)
    assert provider_service.get_provider(mock_sms_notification) == mock_sms_provider


def test_fails_to_initialises_with_unknown_strategy():
    provider_service = ProviderService()

    with pytest.raises(Exception):
        provider_service.init_app(email_provider_selection_strategy_label='UNKNOWN_STRATEGY')
