from app.models import Notification, ProviderDetails


class ProviderService:

    strategy_registry = {}

    def __init__(self):
        self._provider_selection_strategy = None

    def init_app(self, provider_selection_strategy_label: str) -> None:
        try:
            self._provider_selection_strategy = ProviderService.strategy_registry[provider_selection_strategy_label]
        except KeyError:
            raise Exception(
                f"Could not initialise ProviderService with strategy '{provider_selection_strategy_label}' "
                "- has the strategy been declared as a subclass of ProviderSelectionStrategyInterface?"
            )

    @staticmethod
    def register_strategy(cls) -> None:
        ProviderService.strategy_registry[cls.get_label()] = cls

    @property
    def strategy(self):
        return self._provider_selection_strategy

    def get_provider(self, notification: Notification) -> ProviderDetails:
        return self.strategy.get_provider(notification)
