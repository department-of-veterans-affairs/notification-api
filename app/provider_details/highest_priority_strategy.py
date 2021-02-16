from typing import Optional

from app.dao.provider_details_dao import get_highest_priority_active_provider_by_notification_type
from app.notifications.notification_type import NotificationType
from .provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.models import Notification, ProviderDetails


class HighestPriorityStrategy(ProviderSelectionStrategyInterface):
    """
    Provider selection strategy that returns highest priority (lowest number) provider
    """

    @staticmethod
    def get_label() -> str:
        return 'HIGHEST_PRIORITY'

    @staticmethod
    def get_provider(notification: Notification) -> Optional[ProviderDetails]:
        provider = get_highest_priority_active_provider_by_notification_type(
            NotificationType(notification.notification_type),
            notification.international
        )
        return provider
