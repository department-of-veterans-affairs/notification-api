import pytest

from app.models import Notification, ProviderDetails
from app.provider_details.provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.provider_details.provider_service import ProviderService, register_strategy


@register_strategy(label='EXAMPLE_STRATEGY')
class ExampleStrategy(ProviderSelectionStrategyInterface):

    def get_provider(self, notification: Notification) -> ProviderDetails:
        pass


def test_initialises_and_uses_example_strategy(mocker):
    provider_service = ProviderService()
    example_strategy = ExampleStrategy()

    provider_service.init_app(provider_selection_strategy_label='EXAMPLE_STRATEGY')

    mock_provider = mocker.Mock()

    mocker.patch.object(example_strategy, 'get_provider', return_value=mock_provider)

    assert provider_service._provider_selection_strategy == example_strategy

    actual_provider = provider_service.get_provider(mocker.Mock())

    assert actual_provider == mock_provider


def test_fails_to_initialises_with_unknown_strategy():
    provider_service = ProviderService()

    with pytest.raises(Exception):
        provider_service.init_app(provider_selection_strategy_label='UNKNOWN_STRATEGY')
