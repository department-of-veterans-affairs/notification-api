"""
notify_db and notify_db_session are fixtures in tests/conftest.py.

https://docs.sqlalchemy.org/en/13/core/connections.html

Test the stored function va_profile_opt_in_out by calling it directly, and test the lambda function associated
with VA Profile integration calls this stored function.  The stored function should return True if any row was
created or updated; otherwise, False.
"""

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from datetime import datetime, timedelta
from lambda_functions.va_profile.va_profile_opt_in_out_lambda import jwt_is_valid, va_profile_opt_in_out_lambda_handler
from sqlalchemy import text


OPT_IN_OUT = text("""\
SELECT va_profile_opt_in_out(:va_profile_id, :communication_item_id, \
:communication_channel_id, :allowed, :source_datetime);""")

COUNT = r"""SELECT COUNT(*) FROM va_profile_local_cache;"""

VA_PROFILE_TEST = text("""\
SELECT allowed
FROM va_profile_local_cache
WHERE va_profile_id=:va_profile_id \
AND communication_item_id=:communication_item_id \
AND communication_channel_id=:communication_channel_id;""")


@pytest.fixture(scope="module")
def private_key():
    # This assumes tests are run from the project root directory.
    with open("tests/lambda_functions/va_profile/key.pem", "rb") as f:
        private_key_bytes = f.read()

    return serialization.load_pem_private_key(private_key_bytes, password=b"test", backend=default_backend())


@pytest.fixture(scope="module")
def jwt_encoded(private_key):
    """ This is a valid JWT encoding. """

    iat = datetime.now()
    exp = iat + timedelta(minutes=15)
    return jwt.encode({"some": "payload", "exp": exp, "iat": iat}, private_key, algorithm="RS256")


@pytest.fixture()
def jwt_encoded_missing_exp(private_key):
    return jwt.encode({"some": "payload", "iat": datetime.now()}, private_key, algorithm="RS256")


@pytest.fixture()
def jwt_encoded_missing_iat(private_key):
    return jwt.encode({"some": "payload", "exp": datetime.now()}, private_key, algorithm="RS256")


@pytest.fixture()
def jwt_encoded_expired(private_key):
    """ This is an invalid JWT encoding because it is expired. """

    iat = datetime.now() - timedelta(minutes=20)
    exp = iat + timedelta(minutes=15)
    return jwt.encode({"some": "payload", "exp": exp, "iat": iat}, private_key, algorithm="RS256")


@pytest.fixture()
def jwt_encoded_reversed(private_key):
    """
    This JWT encoding has an issue time later than the expiration time.  Both times are in the future.
    """

    exp = datetime.now() + timedelta(days=1)
    iat = exp + timedelta(minutes=15)
    return jwt.encode({"some": "payload", "exp": exp, "iat": iat}, private_key, algorithm="RS256")


def verify_opt_in_status(identifier: int, opted_in: bool, connection):
    """
    Use this helper function to verify that a row's opt-in/out value has been set as expected.
    """

    va_profile_test = VA_PROFILE_TEST.bindparams(
        va_profile_id=identifier,
        communication_item_id=5,
        communication_channel_id=identifier
    )

    profile_test_queryset = connection.execute(va_profile_test)
    stored_preference = profile_test_queryset.fetchone()[0]
    assert stored_preference == opted_in, \
        "The user opted {}.  (allowed={})".format("in" if opted_in else "out", opted_in)


def setup_db(connection):
    """
    Using the given connection, truncate the VA Profile local cache, and call the stored procedure to add a specific
    row.  This establishes a known state for testing.

    Truncating is necessary because the database side effects of executing the VA Profile lambda function are not
    rolled back at the conclusion of a test.
    """

    connection.execute("truncate va_profile_local_cache;")

    # Sanity check
    count_queryset = connection.execute(COUNT)
    assert count_queryset.fetchone()[0] == 0, "The cache should be empty at the start."

    opt_in_out = OPT_IN_OUT.bindparams(
        va_profile_id=0,
        communication_item_id=5,
        communication_channel_id=0,
        allowed=False,
        source_datetime="2022-03-07T19:37:59.320Z"
    )

    in_out_queryset = connection.execute(opt_in_out)
    assert in_out_queryset.fetchone()[0], "The stored function should return True."

    count_queryset = connection.execute(COUNT)
    assert count_queryset.fetchone()[0] == 1, "The stored function should have created a new row."

    verify_opt_in_status(0, False, connection)


def test_va_profile_cache_exists(notify_db):
    assert notify_db.engine.has_table("va_profile_local_cache")


def test_va_profile_stored_function_older_date(notify_db_session):
    """
    If the given date is older than the existing date, no update should occur.
    """

    with notify_db_session.engine.begin() as connection:
        setup_db(connection)

        opt_in_out = OPT_IN_OUT.bindparams(
            va_profile_id=0,
            communication_item_id=5,
            communication_channel_id=0,
            allowed=True,
            source_datetime="2022-02-07T19:37:59.320Z"  # Older date
        )

        in_out_queryset = connection.execute(opt_in_out)
        assert not in_out_queryset.fetchone()[0], "The date is older than the existing entry."

        count_queryset = connection.execute(COUNT)
        assert count_queryset.fetchone()[0] == 1, "The stored function should not have created a new row."

        verify_opt_in_status(0, False, connection)


def test_va_profile_stored_function_newer_date(notify_db_session):
    """
    If the given date is newer than the existing date, an update should occur.
    """

    with notify_db_session.engine.begin() as connection:
        setup_db(connection)

        opt_in_out = OPT_IN_OUT.bindparams(
            va_profile_id=0,
            communication_item_id=5,
            communication_channel_id=0,
            allowed=True,
            source_datetime="2022-04-07T19:37:59.320Z"  # Newer date
        )

        in_out_queryset = connection.execute(opt_in_out)
        assert in_out_queryset.fetchone()[0], "The date is newer than the existing entry."

        count_queryset = connection.execute(COUNT)
        assert count_queryset.fetchone()[0] == 1, "An existing entry should have been updated."

        verify_opt_in_status(0, True, connection)


def test_va_profile_stored_function_new_row(notify_db_session):
    """
    Create a new row for a combination of identifiers not already in the database.
    """

    with notify_db_session.engine.begin() as connection:
        setup_db(connection)

        opt_in_out = OPT_IN_OUT.bindparams(
            va_profile_id=1,
            communication_item_id=5,
            communication_channel_id=1,
            allowed=True,
            source_datetime="2022-02-07T19:37:59.320Z"
        )

        in_out_queryset = connection.execute(opt_in_out)
        assert in_out_queryset.fetchone()[0], "The stored function should have created a new row."

        count_queryset = connection.execute(COUNT)
        assert count_queryset.fetchone()[0] == 2, "The stored function should have created a new row."

        verify_opt_in_status(1, True, connection)


def test_jwt_is_valid(jwt_encoded):
    """
    Test the helper function used to determine if the JWT has a valid signature.
    """

    assert jwt_is_valid(f"Bearer {jwt_encoded}")


@pytest.mark.parametrize("invalid_jwt", [jwt_encoded_missing_exp, jwt_encoded_missing_iat, jwt_encoded_expired, jwt_encoded_reversed])
def test_jwt_invalid(invalid_jwt):
    """
    Any JWT that does not meet this criteria should be invalid:
        - Contains exp claim
        - Contains iat claim
        - exp is not expired
        - exp is after iat
    """

    assert not jwt_is_valid(f"Bearer {invalid_jwt}")


def test_jwt_is_valid_malformed_authorization_header_value(jwt_encoded):
    """
    Test the helper function used to determine if the JWT has a valid signature.
    """

    assert not jwt_is_valid(f"noBearer {jwt_encoded}")


def test_va_profile_opt_in_out_lambda_handler_invalid_jwt():
    """
    Test the VA Profile integration lambda by sending a request with an invalid jwt encoding.
    """

    # https://www.youtube.com/watch?v=a6iW-8xPw3k
    event = create_event("txAuditId", "txAuditId", "2022-03-07T19:37:59.320Z", 0, 0, 5, True, "12345")
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 401, "12345 should not be a valid JWT encoding."


def test_va_profile_opt_in_out_lambda_handler_no_authorization_header():
    """
    Test the VA Profile integration lambda by sending a request without an authorization header.
    """

    event = create_event("txAuditId", "txAuditId", "2022-03-07T19:37:59.320Z", 0, 0, 5, True, '')
    del event["headers"]["Authorization"]
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 401, "Requests without an Authorization header should be invalid."


def test_va_profile_opt_in_out_lambda_handler_missing_attribute(jwt_encoded):
    """
    Test the VA Profile integration lambda by sending a bad request (missing top level attribute).
    """

    event = create_event("txAuditId", "txAuditId", "2022-03-07T19:37:59.320Z", 0, 0, 5, True, jwt_encoded)
    del event["body"]["txAuditId"]
    response = va_profile_opt_in_out_lambda_handler(event, None)
    assert isinstance(response, dict)
    assert response["statusCode"] == 400
    assert response["body"] == "A required top level attribute is missing from the request body or has the wrong type."


def test_va_profile_opt_in_out_lambda_handler_new_row(notify_db, worker_id, jwt_encoded):
    """
    Test the VA Profile integration lambda by sending a valid request that should create
    a new row in the database.
    """

    with notify_db.engine.begin() as connection:
        setup_db(connection)

    # Send a request that should result in a new row.
    event = create_event("txAuditId", "txAuditId", "2022-03-07T19:37:59.320Z", 1, 1, 5, True, jwt_encoded)
    response = va_profile_opt_in_out_lambda_handler(event, None, worker_id)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200

    with notify_db.engine.begin() as connection:
        count_queryset = connection.execute(COUNT)
        assert count_queryset.fetchone()[0] == 2, "A new row should have been created."

        verify_opt_in_status(1, True, connection)


def test_va_profile_opt_in_out_lambda_handler_older_date(notify_db, worker_id, jwt_encoded):
    """
    Test the VA Profile integration lambda by sending a valid request with an older date.
    No database update should occur.
    """

    with notify_db.engine.begin() as connection:
        setup_db(connection)

    event = create_event("txAuditId", "txAuditId", "2022-02-07T19:37:59.320Z", 0, 0, 5, True, jwt_encoded)
    response = va_profile_opt_in_out_lambda_handler(event, None, worker_id)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200

    with notify_db.engine.begin() as connection:
        count_queryset = connection.execute(COUNT)
        assert count_queryset.fetchone()[0] == 1, "A new row should not have been created."

        verify_opt_in_status(0, False, connection)


def test_va_profile_opt_in_out_lambda_handler_newer_date(notify_db, worker_id, jwt_encoded):
    """
    Test the VA Profile integration lambda by sending a valid request with a newer date.
    A database update should occur.
    """

    with notify_db.engine.begin() as connection:
        setup_db(connection)

    event = create_event("txAuditId", "txAuditId", "2022-04-07T19:37:59.320Z", 0, 0, 5, True, jwt_encoded)
    response = va_profile_opt_in_out_lambda_handler(event, None, worker_id)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200

    with notify_db.engine.begin() as connection:
        count_queryset = connection.execute(COUNT)
        assert count_queryset.fetchone()[0] == 1, "A new row should not have been created."

        verify_opt_in_status(0, True, connection)


@pytest.mark.skip(reason="need to test PUT response")
def test_va_profile_opt_in_out_lambda_handler_PUT():
    """
    Test the VA Profile integration lambda by inspecting the PUT request is initiates to
    VA Profile in response to a request.
    """

    raise NotImplementedError


@pytest.mark.skip(reason="need to test PUT response")
def test_va_profile_opt_in_out_lambda_handler_wrong_communication_channel_id(worker_id, jwt_encoded):
    """
    The lambda should ignore records in which communicationChannelId is not 5.
    """

    event = create_event("tx_audit_id", "2022-04-27T16:57:16Z", 2, 3, 4, True, jwt_encoded)
    response = va_profile_opt_in_out_lambda_handler(event, None, worker_id)
    assert isinstance(response, dict)
    assert response["statusCode"] == 200
    # TODO - More testing.


def create_event(
        master_tx_audit_id: str,
        tx_audit_id: str,
        source_date: str,
        va_profile_id: int,
        communication_channel_id: int,
        communication_item_id: int,
        is_allowed: bool,
        jwt_value) -> dict:
    """
    Return a dictionary in the format of the payload the lambda function expects to
    receive from VA Profile via AWS API Gateway v2.
    """

    return {
        "headers": {
            "Authorization": f"Bearer {jwt_value}",
        },
        "body": {
            "txAuditId": master_tx_audit_id,
            "bios": [
                create_bios_element(
                    tx_audit_id,
                    source_date,
                    va_profile_id,
                    communication_channel_id,
                    communication_item_id, is_allowed
                )
            ],
        },
    }


def create_bios_element(
        tx_audit_id: str,
        source_date: str,
        va_profile_id: int,
        communication_channel_id: int,
        communication_item_id: int,
        is_allowed: bool) -> dict:

    return {
        "txAuditId": tx_audit_id,
        "sourceDate": source_date,
        "vaProfileId": va_profile_id,
        "communicationChannelId": communication_channel_id,
        "communicationItemId": communication_item_id,
        "allowed": is_allowed,
    }
