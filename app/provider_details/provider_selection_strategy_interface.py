from app.models import ProviderDetails, Notification
from app.provider_details.provider_service import ProviderService


class ProviderSelectionStrategyInterface:
    """
    Abstract class as interface for provider selection strategies.

    Strategies that inherit from this interface, once imported, will be added to ProviderService.strategy_registry
    We import strategies in the provider_details module __init__.py to achieve this.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        ProviderService.register_strategy(cls)

    @staticmethod
    def get_label() -> str:
        raise NotImplementedError()

    @staticmethod
    def get_provider(notification: Notification) -> ProviderDetails:
        raise NotImplementedError()
