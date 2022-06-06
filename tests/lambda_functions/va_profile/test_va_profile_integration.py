"""
notify_db and notify_db_session are fixtures in tests/conftest.py.

https://docs.sqlalchemy.org/en/13/core/connections.html

Truncating the va_profile_local_cache table at the beginning and end of some tests is necessary because the database
side effects of executing the VA Profile lambda function are not rolled back at the conclusion of a test.
"""

from lambda_functions.va_profile.va_profile_opt_in_out_lambda import va_profile_opt_in_out_lambda_handler
from sqlalchemy import text


OPT_IN_OUT = text("""SELECT va_profile_opt_in_out(:va_profile_id, :communication_item_id, :communication_channel_id, :allowed, :source_datetime);""")

COUNT = r"""SELECT COUNT(*) FROM va_profile_local_cache;"""

VA_PROFILE_TEST = text("""\
SELECT allowed
FROM va_profile_local_cache
WHERE va_profile_id=:va_profile_id AND communication_item_id=:communication_item_id AND communication_channel_id=:communication_channel_id;""")


def test_va_profile_cache_exists(notify_db):
    assert notify_db.engine.has_table("va_profile_local_cache")


def test_va_profile_opt_in_out(notify_db_session):
    """
    Test the stored function va_profile_opt_in_out by calling it directly.  The lambda function associated with
    VA Profile integration calls this stored function.  The stored function should return True if any row was
    created or updated; otherwise, False.
    """

    with notify_db_session.engine.begin() as connection:
        # Begin with a sanity check.
        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 0, "The cache should be empty at the start."

        opt_in_out = OPT_IN_OUT.bindparams(
            va_profile_id=0,
            communication_item_id=0,
            communication_channel_id=0,
            allowed=False,
            source_datetime="2022-03-07T19:37:59.320Z"
        )

        va_profile_test = VA_PROFILE_TEST.bindparams(
            va_profile_id=0,
            communication_item_id=0,
            communication_channel_id=0
        )

        result = connection.execute(opt_in_out)
        assert result.fetchone()[0], "The stored function should return True."

        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 1, "The stored function should have created a new row."

        result = connection.execute(va_profile_test)
        assert not result.fetchone()[0], "The user opted out.  (allowed=False)"

        opt_in_out = OPT_IN_OUT.bindparams(
            va_profile_id=0,
            communication_item_id=0,
            communication_channel_id=0,
            allowed=True,
            source_datetime="2022-02-07T19:37:59.320Z"  # Older date
        )

        result = connection.execute(opt_in_out)
        assert not result.fetchone()[0], "The date is older than the existing entry."

        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 1, "The stored function should not have created a new row."

        result = connection.execute(va_profile_test)
        assert not result.fetchone()[0], "The user should still be opted out.  (allowed=False)"

        opt_in_out = OPT_IN_OUT.bindparams(
            va_profile_id=0,
            communication_item_id=0,
            communication_channel_id=0,
            allowed=True,
            source_datetime="2022-04-07T19:37:59.320Z"  # Newer date
        )

        result = connection.execute(opt_in_out)
        assert result.fetchone()[0], "The date is newer than the existing entry."

        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 1, "An existing entry should have been updated."

        result = connection.execute(va_profile_test)
        assert result.fetchone()[0], "The user should be opted in.  (allowed=True)"

        opt_in_out = OPT_IN_OUT.bindparams(
            va_profile_id=1,
            communication_item_id=1,
            communication_channel_id=1,
            allowed=True,
            source_datetime="2022-02-07T19:37:59.320Z"
        )

        va_profile_test = VA_PROFILE_TEST.bindparams(
            va_profile_id=1,
            communication_item_id=1,
            communication_channel_id=1
        )

        result = connection.execute(opt_in_out)
        assert result.fetchone()[0], "The stored function should have created a new row."

        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 2, "The stored function should have created a new row."

        result = connection.execute(va_profile_test)
        assert result.fetchone()[0], "The user should be opted in.  (allowed=True)"


def test_handler_va_profile_opt_in_out_lambda_missing_attribute():
    """
    Test the VA Profile integration lambda by sending a bad request (missing top level attribute).
    """

    event = create_event("txAuditId", "txAuditId", "2022-03-07T19:37:59.320Z", 0, 0, 0, True)
    del event["txAuditId"]
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 400
    assert response["body"] == "A required top level attribute is missing from the request or has the wrong type."


def test_handler_va_profile_opt_in_out_lambda_valid_requests(notify_db):
    """
    Test the VA Profile integration lambda by sending valid requests that do not result in a PUT
    request to VA Profile (because the .pem chain is None in the lambda code).    
    """

    with notify_db.engine.begin() as connection:
        connection.execute("truncate va_profile_local_cache;")

        # Begin with a sanity check.
        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 0, "The cache should be empty at the start."

    # Send a request that should result in a new row.
    event = create_event("txAuditId", "txAuditId", "2022-03-07T19:37:59.320Z", 0, 0, 0, True)
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200

    va_profile_test = VA_PROFILE_TEST.bindparams(
        va_profile_id=0,
        communication_item_id=0,
        communication_channel_id=0
    )

    with notify_db.engine.begin() as connection:
        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 1, "A new row should have been created."

        result = connection.execute(va_profile_test)
        assert result.fetchone()[0], "The user opted in.  (allowed=True)"

    # Send a request that should not affect the database (older date).
    event = create_event("txAuditId", "txAuditId", "2022-02-07T19:37:59.320Z", 0, 0, 0, False)
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200

    with notify_db.engine.begin() as connection:
        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 1, "A new row should not have been created."

        result = connection.execute(va_profile_test)
        assert result.fetchone()[0], "The user should remain opted in.  (allowed=True)"


    # Send a request that should update the database (newer date).
    event = create_event("txAuditId", "txAuditId", "2022-04-07T19:37:59.320Z", 0, 0, 0, False)
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200

    with notify_db.engine.begin() as connection:
        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 1, "A new row should not have been created."

        result = connection.execute(va_profile_test)
        assert not result.fetchone()[0], "The user opted out.  (allowed=False)"

    # Send another request that should result in a new row.
    event = create_event("txAuditId", "txAuditId", "2022-03-07T19:37:59.320Z", 1, 1, 1, True)
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200

    va_profile_test = VA_PROFILE_TEST.bindparams(
        va_profile_id=1,
        communication_item_id=1,
        communication_channel_id=1
    )

    with notify_db.engine.begin() as connection:
        result = connection.execute(COUNT)
        assert result.fetchone()[0] == 2, "A new row should have been created."

        result = connection.execute(va_profile_test)
        assert result.fetchone()[0], "The user opted in.  (allowed=True)"

        connection.execute("truncate va_profile_local_cache;")


def test_handler_va_profile_opt_in_out_lambda_PUT():
    """
    Test the VA Profile integration lambda by inspecting the PUT request is initiates to
    VA Profile in response to a request.
    """

    pass


def create_event(master_tx_audit_id: str, tx_audit_id: str, source_date: str, va_profile_id: int, communication_channel_id: int, communication_item_id: int, is_allowed: bool) -> dict:
    """
    Return a dictionary in the format of the payload the lambda function expects to receive from VA Profile.
    """

    return {
        "txAuditId": master_tx_audit_id,
        "bios": [
            create_bios_element(tx_audit_id, source_date, va_profile_id, communication_channel_id, communication_item_id, is_allowed)
        ]
    }


def create_bios_element(tx_audit_id: str, source_date: str, va_profile_id: int, communication_channel_id: int, communication_item_id: int, is_allowed: bool) -> dict:
    return {
        "txAuditId": tx_audit_id,
        "sourceDate": source_date,
        "vaProfileId": va_profile_id,
        "communicationChannelId": communication_channel_id,
        "communicationItemId": communication_item_id,
        "allowed": is_allowed,
    }

