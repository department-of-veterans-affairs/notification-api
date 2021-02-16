from .highest_priority_strategy import HighestPriorityStrategy
from .load_balancing_strategy import LoadBalancingStrategy

strategy_map = {
    'HighestPriorityStrategy': HighestPriorityStrategy,
    'LoadBalancingStrategy': LoadBalancingStrategy
}


class ProviderService:

    def init_app(self, provider_selection_strategy_name: str) -> None:
        self.provider_selection_strategy = strategy_map[provider_selection_strategy_name]()
