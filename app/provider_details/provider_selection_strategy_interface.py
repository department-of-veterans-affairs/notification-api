from app.models import ProviderDetails, Notification


class ProviderSelectionStrategyInterface:
    """
    Abstract class as interface for provider selection strategies
    """

    def get_provider(self, notification: Notification) -> ProviderDetails:
        raise NotImplementedError()
