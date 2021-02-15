from .provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.models import ProviderDetails
from app.notifications.notification_type import NotificationType


class LoadBalancingStrategy(ProviderSelectionStrategyInterface):
    """
    Provider selection strategy that returns random provider based on
    configured weights stored in provider_details table
    """

    def get_provider(self, notification_type: NotificationType) -> ProviderDetails:
        pass
