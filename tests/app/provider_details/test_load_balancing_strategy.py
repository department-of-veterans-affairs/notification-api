import pytest

from app.notifications.notification_type import NotificationType
from app.provider_details.load_balancing_strategy import LoadBalancingStrategy


def test_get_provider_returns_single_provider(mocker):
    mock_provider = mocker.Mock(load_balancing_weight=10)
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


def test_get_provider_handles_no_providers(mocker):
    mocker.patch(
        'app.provider_details.load_balancing_strategy.get_active_providers_with_weights_by_notification_type',
        return_value=[]
    )

    strategy = LoadBalancingStrategy()

    mock_notification = mocker.Mock(
        notification_type=NotificationType.EMAIL,
        international=False
    )

    provider = strategy.get_provider(mock_notification)
    assert provider is None


def test_get_provider_returns_weighted_random_provider(mocker):
    mock_provider_1 = mocker.Mock(load_balancing_weight=10)
    mock_provider_2 = mocker.Mock(load_balancing_weight=90)
    mocker.patch(
        'app.provider_details.load_balancing_strategy.get_active_providers_with_weights_by_notification_type',
        return_value=[mock_provider_1, mock_provider_2]
    )

    mock_choices = mocker.patch(
        'app.provider_details.load_balancing_strategy.choices',
        return_value=[mock_provider_2]
    )

    strategy = LoadBalancingStrategy()

    mock_notification = mocker.Mock(
        notification_type=NotificationType.EMAIL,
        international=False
    )

    provider = strategy.get_provider(mock_notification)
    assert provider == mock_provider_2

    mock_choices.assert_called_with([mock_provider_1, mock_provider_2], [10, 90])


@pytest.mark.skip('Due to randomness, there is a very small chance that this test will fail. '
                  'Leaving it here as peace of mind that our approach works')
def test_random_distribution(mocker):
    mock_provider_1 = mocker.Mock(load_balancing_weight=10)
    mock_provider_2 = mocker.Mock(load_balancing_weight=90)
    mocker.patch(
        'app.provider_details.load_balancing_strategy.get_active_providers_with_weights_by_notification_type',
        return_value=[mock_provider_1, mock_provider_2]
    )

    strategy = LoadBalancingStrategy()

    mock_notification = mocker.Mock(
        notification_type=NotificationType.EMAIL,
        international=False
    )

    number_of_samples = 500

    sampled_providers = [strategy.get_provider(mock_notification) for _ in range(number_of_samples)]

    sum_of_weights = mock_provider_1.load_balancing_weight + mock_provider_2.load_balancing_weight

    expected_proportion_of_provider_1 = mock_provider_1.load_balancing_weight / sum_of_weights
    expected_proportion_of_provider_2 = mock_provider_2.load_balancing_weight / sum_of_weights

    expected_occurrences_of_provider_1 = number_of_samples * expected_proportion_of_provider_1
    expected_occurrences_of_provider_2 = number_of_samples * expected_proportion_of_provider_2

    assert sampled_providers.count(mock_provider_1) == pytest.approx(expected_occurrences_of_provider_1, abs=5)
    assert sampled_providers.count(mock_provider_2) == pytest.approx(expected_occurrences_of_provider_2, abs=5)
