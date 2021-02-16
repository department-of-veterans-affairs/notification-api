from app.notifications.notification_type import NotificationType
from app.provider_details.highest_priority_strategy import HighestPriorityStrategy


def test_get_provider_returns_highest_priority_provider(mocker):
    mock_provider = mocker.Mock()
    mock_dao_get_provider = mocker.patch(
        'app.provider_details.highest_priority_strategy.get_highest_priority_active_provider_by_notification_type',
        return_value=mock_provider
    )

    strategy = HighestPriorityStrategy()

    mock_notification = mocker.Mock(
        notification_type=NotificationType.EMAIL,
        international=False
    )

    provider = strategy.get_provider(mock_notification)
    assert provider == mock_provider

    mock_dao_get_provider.assert_called_with(NotificationType.EMAIL, False)
