from app.dao.provider_details_dao import get_highest_priority_active_provider_by_notification_type
from app.notifications.notification_type import NotificationType
from app.models import ProviderDetails, Notification
from .provider_selection_strategy_interface import ProviderSelectionStrategyInterface


class HighestPriorityStrategy(ProviderSelectionStrategyInterface):
    """
    Provider selection strategy that returns highest priority (lowest number) provider
    """

    def get_provider(self, notification: Notification) -> ProviderDetails:
        provider = get_highest_priority_active_provider_by_notification_type(
            NotificationType(notification.notification_type),
            notification.international
        )
        return provider
