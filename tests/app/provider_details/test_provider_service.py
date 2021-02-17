import pytest

from app.models import Notification, ProviderDetails, Template, Service
from app.notifications.notification_type import NotificationType
from app.provider_details.provider_selection_strategy_interface import ProviderSelectionStrategyInterface
from app.provider_details.provider_service import ProviderService


class ExampleEmailStrategy(ProviderSelectionStrategyInterface):

    @staticmethod
    def get_label() -> str:
        return 'EXAMPLE_EMAIL_STRATEGY'

    @staticmethod
    def get_provider(notification: Notification) -> ProviderDetails:
        pass


class ExampleSmsStrategy(ProviderSelectionStrategyInterface):

    @staticmethod
    def get_label() -> str:
        return 'EXAMPLE_SMS_STRATEGY'

    @staticmethod
    def get_provider(notification: Notification) -> ProviderDetails:
        pass


@pytest.fixture
def provider_service():
    provider_service = ProviderService()
    provider_service.init_app(
        email_provider_selection_strategy_label='EXAMPLE_EMAIL_STRATEGY',
        sms_provider_selection_strategy_label='EXAMPLE_SMS_STRATEGY'
    )

    assert provider_service.strategies[NotificationType.EMAIL] == ExampleEmailStrategy
    assert provider_service.strategies[NotificationType.SMS] == ExampleSmsStrategy

    return provider_service


def test_returns_template_provider(mocker, provider_service):

    template_with_provider = mocker.Mock(Template, provider_id='some-id')

    mock_notification = mocker.Mock(Notification, template=template_with_provider)

    mock_provider = mocker.Mock(ProviderDetails)
    mock_get_provider_details = mocker.patch(
        'app.provider_details.provider_service.get_provider_details_by_id',
        return_value=mock_provider
    )

    assert mock_provider == provider_service.get_provider(mock_notification)

    mock_get_provider_details.assert_called_with('some-id')


@pytest.mark.parametrize(
    'notification_type, expected_provider_id', [
        (NotificationType.EMAIL, 'email-provider-id'),
        (NotificationType.SMS, 'sms-provider-id')
    ]
)
def test_returns_service_provider_for_notification_type_if_no_template_provider(
        mocker,
        provider_service,
        notification_type,
        expected_provider_id
):
    template_without_provider = mocker.Mock(Template, provider_id=None)

    service_with_providers = mocker.Mock(
        Service,
        email_provider_id='email-provider-id',
        sms_provider_id='sms-provider-id'
    )

    mock_notification = mocker.Mock(
        Notification,
        notification_type=notification_type,
        template=template_without_provider,
        service=service_with_providers
    )

    mock_provider = mocker.Mock(ProviderDetails)
    mock_get_provider_details = mocker.patch(
        'app.provider_details.provider_service.get_provider_details_by_id',
        return_value=mock_provider
    )

    assert mock_provider == provider_service.get_provider(mock_notification)

    mock_get_provider_details.assert_called_with(expected_provider_id)


@pytest.mark.parametrize(
    'notification_type, expected_strategy', [
        (NotificationType.EMAIL, ExampleEmailStrategy),
        (NotificationType.SMS, ExampleSmsStrategy)
    ]
)
def test_uses_strategy_for_notification_type_when_no_template_or_service_providers(
        mocker,
        provider_service,
        notification_type,
        expected_strategy
):
    template_without_provider = mocker.Mock(Template, provider_id=None)
    service_without_providers = mocker.Mock(Service, email_provider_id=None, sms_provider_id=None)

    provider = mocker.Mock()
    mocker.patch.object(expected_strategy, 'get_provider', return_value=provider)

    notification = mocker.Mock(
        notification_type=notification_type,
        template=template_without_provider,
        service=service_without_providers
    )

    assert provider_service.get_provider(notification) == provider
    expected_strategy.get_provider.assert_called_with(notification)


def test_fails_to_initialises_with_unknown_email_strategy():
    provider_service = ProviderService()

    with pytest.raises(Exception):
        provider_service.init_app(
            email_provider_selection_strategy_label='UNKNOWN_EMAIL_STRATEGY',
            sms_provider_selection_strategy_label='EXAMPLE_SMS_STRATEGY'
        )


def test_fails_to_initialises_with_unknown_sms_strategy():
    provider_service = ProviderService()

    with pytest.raises(Exception):
        provider_service.init_app(
            email_provider_selection_strategy_label='EXAMPLE_EMAIL_STRATEGY',
            sms_provider_selection_strategy_label='UNKNOWN_SMS_STRATEGY'
        )
