

def test_get_providers_returns_highest_priority_provider(mocker, restore_provider_details, sample_notification):
    pass
    # providers = provider_details_dao.get_provider_details_by_notification_type('sms')
    #
    # first = providers[0]
    # second = providers[1]
    #
    # assert send_to_providers.provider_to_use('sms', sample_notification).name == first.identifier
    #
    # first.priority, second.priority = second.priority, first.priority
    #
    # provider_details_dao.dao_update_provider_details(first)
    # provider_details_dao.dao_update_provider_details(second)
    #
    # assert send_to_providers.provider_to_use('sms', sample_notification).name == second.identifier
    #
    # first.priority, second.priority = second.priority, first.priority
    # first.active = False
    #
    # provider_details_dao.dao_update_provider_details(first)
    # provider_details_dao.dao_update_provider_details(second)
    #
    # assert send_to_providers.provider_to_use('sms', sample_notification).name == second.identifier
    #
    # first.active = True
    # provider_details_dao.dao_update_provider_details(first)
    #
    # assert send_to_providers.provider_to_use('sms', sample_notification).name == first.identifier
