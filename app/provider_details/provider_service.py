import functools

strategy_map = {}


def register_strategy(label: str):
    def decorator_register_strategy(_class):
        @functools.wraps(_class)
        def strategy_class(*args, **kwargs):
            strategy = _class(*args, **kwargs)
            strategy_map[label] = strategy
            return strategy
        return strategy_class
    return decorator_register_strategy


class ProviderService:

    def init_app(self, provider_selection_strategy_label: str) -> None:
        try:
            self.provider_selection_strategy = strategy_map[provider_selection_strategy_label]
        except KeyError:
            raise Exception(
                f"Could not initialise ProviderService with strategy '{provider_selection_strategy_label}' "
                "- has the strategy been initialised and registered?"
            )
