from typing import Optional

from app.dao.provider_details_dao import get_highest_priority_active_provider_identifier_by_notification_type
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
    def validate(notification_type: NotificationType) -> None:
        if get_highest_priority_active_provider_identifier_by_notification_type(notification_type) is None:
            raise Exception(
                f'Highest Priority Strategy cannot be used for {notification_type} notifications '
                'because there are no matching active providers'
            )

    @staticmethod
    def get_provider(notification: Notification) -> str | None:
        return get_highest_priority_active_provider_identifier_by_notification_type(
            NotificationType(notification.notification_type), notification.international
        )
