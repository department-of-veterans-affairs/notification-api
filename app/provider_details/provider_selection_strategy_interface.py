from moto.s3.models import Notification

from app.models import ProviderDetails


class ProviderSelectionStrategyInterface:
    """
    Abstract class as interface for provider selection strategies
    """

    def get_provider(self, notification: Notification) -> ProviderDetails:
        raise NotImplementedError()
