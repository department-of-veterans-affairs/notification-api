from .provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.models import ProviderDetails, Notification
from app.notifications.notification_type import NotificationType
from app.dao.provider_details_dao import get_active_providers_with_weights_by_notification_type


class LoadBalancingStrategy(ProviderSelectionStrategyInterface):
    """
    Provider selection strategy that returns random provider based on
    configured weights stored in provider_details table
    """

    def get_provider(self, notification: Notification) -> ProviderDetails:
        providers = get_active_providers_with_weights_by_notification_type(
            NotificationType(notification.notification_type),
            notification.international
        )

        return providers[0]
