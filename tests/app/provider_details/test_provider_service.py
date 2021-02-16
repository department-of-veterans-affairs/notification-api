import pytest

from app.models import Notification, ProviderDetails
from app.provider_details.provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.provider_details.provider_service import ProviderService, register_strategy


@register_strategy(label='EXAMPLE_STRATEGY')
class ExampleStrategy(ProviderSelectionStrategyInterface):

    def get_provider(self, notification: Notification) -> ProviderDetails:
        pass


def test_initialises_with_example_strategy():
    provider_service = ProviderService()
    example_strategy = ExampleStrategy()

    provider_service.init_app(provider_selection_strategy_label='EXAMPLE_STRATEGY')

    assert provider_service.provider_selection_strategy == example_strategy


def test_fails_to_initialises_with_unknown_strategy():
    provider_service = ProviderService()

    with pytest.raises(Exception):
        provider_service.init_app(provider_selection_strategy_label='UNKNOWN_STRATEGY')
