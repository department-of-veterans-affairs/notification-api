from app.notifications.notification_type import NotificationType
from app.provider_details.load_balancing_strategy import LoadBalancingStrategy


def test_get_provider_returns_single_provider(mocker):
    mock_provider = mocker.Mock()
    mock_dao_get_provider = mocker.patch(
        'app.provider_details.load_balancing_strategy.get_active_providers_with_weights_by_notification_type',
        return_value=[mock_provider]
    )

    strategy = LoadBalancingStrategy()

    mock_notification = mocker.Mock(
        notification_type=NotificationType.EMAIL,
        international=False
    )

    provider = strategy.get_provider(mock_notification)
    assert provider == mock_provider

    mock_dao_get_provider.assert_called_with(NotificationType.EMAIL, False)
