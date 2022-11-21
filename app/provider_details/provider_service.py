from app.dao.provider_details_dao import get_provider_details_by_id
from app.exceptions import InvalidProviderException
from app.models import Notification, ProviderDetails
from app.notifications.notification_type import NotificationType
from app.provider_details.provider_selection_strategy_interface import (
    ProviderSelectionStrategyInterface,
    STRATEGY_REGISTRY,
)
from typing import Type, Dict, Optional


class ProviderService:

    def __init__(self):
        self._strategies: Dict[NotificationType, Optional[Type[ProviderSelectionStrategyInterface]]] = {
            NotificationType.EMAIL: None,
            NotificationType.SMS: None
        }

    def init_app(
            self,
            email_provider_selection_strategy_label: str,
            sms_provider_selection_strategy_label: str
    ) -> None:
        try:
            email_strategy = STRATEGY_REGISTRY[email_provider_selection_strategy_label]
            sms_strategy = STRATEGY_REGISTRY[sms_provider_selection_strategy_label]
        except KeyError as e:
            [failed_key] = e.args
            raise Exception(
                f"Could not initialise ProviderService with strategy '{failed_key}' "
                "- has the strategy been declared as a subclass of ProviderSelectionStrategyInterface?"
            )
        else:
            self._strategies[NotificationType.EMAIL] = email_strategy
            self._strategies[NotificationType.SMS] = sms_strategy

    @property
    def strategies(self):
        return self._strategies

    def validate_strategies(self) -> None:
        for notification_type, strategy in self.strategies.items():
            strategy.validate(notification_type)

    def get_provider(self, notification: Notification) -> ProviderDetails:
        """
        Return an instance of ProviderDetails.
        """

        # This is a UUID (ProviderDetails primary key) or None.
        provider_id: Optional[str] = self._get_template_or_service_provider_id(notification)

        if provider_id is None:
            if notification.notification_type == NotificationType.SMS:
                # Do not use any other criteria to determine the provider.  See notification-api#944.
                provider = None
                provider_selection_strategy = None
            else:
                provider_selection_strategy = self._strategies[NotificationType(notification.notification_type)]
                provider = provider_selection_strategy.get_provider(notification)

            if provider is None:
                exception_message = "could not find a suitable provider"

                if provider_selection_strategy is not None:
                    exception_message = provider_selection_strategy.get_label() + ' ' + exception_message

                raise InvalidProviderException(exception_message)
        else:
            provider = get_provider_details_by_id(provider_id)

            if provider is None:
                raise InvalidProviderException(f'provider {provider_id} could not be found')
            elif not provider.active:
                raise InvalidProviderException(f'provider {provider_id} is not active')

        return provider

    @staticmethod
    def _get_template_or_service_provider_id(notification: Notification) -> Optional[str]:
        """
        Return a primary key for an instance of ProviderDetails using this criteria:
            1. Use the notification template's provider_id first.
            2. Use the notification service's provider_id if the template's provider_id is null.

        The return value, if not None, is a UUID.
        """

        # The template provider_id is nullable.
        if notification.template.provider_id is not None:
            return notification.template.provider_id

        # A template provider_id is not available.  Try using a service provider_id, which might also be None.
        if notification.notification_type == NotificationType.EMAIL:
            return notification.service.email_provider_id
        elif notification.notification_type == NotificationType.SMS:
            return notification.service.sms_provider_id
        # TODO - What about letters?  That is the 3rd enumerated value in NotificationType
        # and Notification.notification_type.

        assert False, f"Unanticipated notification type: {notification.notification_type}"
        return None
