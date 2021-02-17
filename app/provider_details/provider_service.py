from typing import Type, Dict, Optional

from app.models import Notification, ProviderDetails
from app.notifications.notification_type import NotificationType
from app.provider_details.provider_selection_strategy_interface import ProviderSelectionStrategyInterface, \
    STRATEGY_REGISTRY


class ProviderService:

    def __init__(self):
        self._strategies: Dict[NotificationType, Optional[Type[ProviderSelectionStrategyInterface]]] = {
            notification_type: None for notification_type in NotificationType
        }

    def init_app(
            self,
            email_provider_selection_strategy_label: str,
            sms_provider_selection_strategy_label: str
    ) -> None:
        try:
            self._strategies[NotificationType.EMAIL] = STRATEGY_REGISTRY[email_provider_selection_strategy_label]
            self._strategies[NotificationType.SMS] = STRATEGY_REGISTRY[sms_provider_selection_strategy_label]
        except KeyError as e:
            [failed_key] = e.args
            raise Exception(
                f"Could not initialise ProviderService with strategy '{failed_key}' "
                "- has the strategy been declared as a subclass of ProviderSelectionStrategyInterface?"
            )

    @property
    def strategies(self):
        return self._strategies

    def get_provider(self, notification: Notification) -> ProviderDetails:
        provider_selection_strategy = self._strategies[NotificationType(notification.notification_type)]
        return provider_selection_strategy.get_provider(notification)
