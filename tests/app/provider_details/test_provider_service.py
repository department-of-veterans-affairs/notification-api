import pytest

from app.models import Notification, ProviderDetails
from app.provider_details.provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.provider_details.provider_service import ProviderService


class ExampleStrategy(ProviderSelectionStrategyInterface):

    @staticmethod
    def get_label() -> str:
        return 'EXAMPLE_STRATEGY'

    @staticmethod
    def get_provider(notification: Notification) -> ProviderDetails:
        pass


def test_initialises_and_uses_example_strategy(mocker):
    provider_service = ProviderService()
    provider_service.init_app(provider_selection_strategy_label='EXAMPLE_STRATEGY')

    mock_provider = mocker.Mock()
    mocker.patch.object(ExampleStrategy, 'get_provider', return_value=mock_provider)

    assert provider_service.strategy == ExampleStrategy

    actual_provider = provider_service.get_provider(mocker.Mock())

    assert actual_provider == mock_provider


def test_fails_to_initialises_with_unknown_strategy():
    provider_service = ProviderService()

    with pytest.raises(Exception):
        provider_service.init_app(provider_selection_strategy_label='UNKNOWN_STRATEGY')
