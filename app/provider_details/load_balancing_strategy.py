from random import choices
from typing import Optional

from .provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from .provider_service import register_strategy
from app.models import ProviderDetails, Notification
from app.notifications.notification_type import NotificationType
from app.dao.provider_details_dao import get_active_providers_with_weights_by_notification_type


@register_strategy(label='LOAD_BALANCING')
class LoadBalancingStrategy(ProviderSelectionStrategyInterface):
    """
    Provider selection strategy that returns random provider based on
    configured weights stored in provider_details table
    """

    def get_provider(self, notification: Notification) -> Optional[ProviderDetails]:
        providers = get_active_providers_with_weights_by_notification_type(
            NotificationType(notification.notification_type),
            notification.international
        )

        if providers:
            [randomly_chosen_provider] = choices(providers, [provider.load_balancing_weight for provider in providers])
            return randomly_chosen_provider
