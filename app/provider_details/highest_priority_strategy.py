from .provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.models import ProviderDetails
from app.notifications.notification_type import NotificationType


class HighestPriorityStrategy(ProviderSelectionStrategyInterface):
    """
    Provider selection strategy that returns highest priority (lowest number) provider
    """

    def get_provider(self, notification_type: NotificationType) -> ProviderDetails:
        pass
