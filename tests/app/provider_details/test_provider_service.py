from app.provider_details.highest_priority_strategy import HighestPriorityStrategy
from app.provider_details.load_balancing_strategy import LoadBalancingStrategy
from app.provider_details.provider_service import ProviderService


def test_initialises_with_highest_priority_strategy():
    provider_service = ProviderService()
    provider_service.init_app(provider_selection_strategy_name='HighestPriorityStrategy')

    assert type(provider_service.provider_selection_strategy) is HighestPriorityStrategy


def test_initialises_with_load_balancing_strategy():
    provider_service = ProviderService()
    provider_service.init_app(provider_selection_strategy_name='LoadBalancingStrategy')

    assert type(provider_service.provider_selection_strategy) is LoadBalancingStrategy
