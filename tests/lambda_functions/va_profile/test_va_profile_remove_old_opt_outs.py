from sqlalchemy import text
from datetime import datetime, timedelta

INSERT_OPT_IN_OUT_RECORD = text(
    """INSERT INTO va_profile_local_cache(va_profile_id, communication_item_id,
    communication_channel_id, source_datetime, allowed)
    VALUES(:va_profile_id, :communication_item_id, :communication_channel_id,
    :source_datetime, :allowed)"""
)

REMOVE_OPTED_OUT_RECORDS_QUERY = text("""SELECT va_profile_remove_old_opt_outs();""")

COUNT = r"""SELECT COUNT(*) FROM va_profile_local_cache;"""

COUNT_OPTED_OUT_RECORD_QUERY = text("""SELECT COUNT(*)
FROM va_profile_local_cache
WHERE allowed = False
AND age(NOW(), source_datetime) > INTERVAL '24 hours';""")


def setup_db(connection):
    """
    Using the given connection, truncate the VA Profile local cache, and call
    the stored procedure to add a specific row. This establishes a known state
    for testing. Truncating is necessary because the database side effects of
    executing the VA Profile lambda function are not rolled back at the
    conclusion of a test.
    """

    connection.execute("truncate va_profile_local_cache;")

    # Sanity check
    count_queryset = connection.execute(COUNT)
    assert count_queryset.fetchone()[0] == 0, "The cache should be empty at the start."

    expired_datetime = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S%z')

    insert_expired_record_opt_out = INSERT_OPT_IN_OUT_RECORD.bindparams(
        va_profile_id=0,
        communication_item_id=0,
        communication_channel_id=0,
        allowed=False,
        source_datetime=expired_datetime
    )

    connection.execute(insert_expired_record_opt_out)

    insert_expired_record_opt_in = INSERT_OPT_IN_OUT_RECORD.bindparams(
        va_profile_id=2,
        communication_item_id=3,
        communication_channel_id=4,
        allowed=True,
        source_datetime=expired_datetime
    )

    connection.execute(insert_expired_record_opt_in)

    insert_active_record_opt_out = INSERT_OPT_IN_OUT_RECORD.bindparams(
        va_profile_id=1,
        communication_item_id=2,
        communication_channel_id=3,
        allowed=False,
        source_datetime=datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')
    )

    connection.execute(insert_active_record_opt_out)

    count_records_currently_in_database = connection.execute(COUNT)
    assert count_records_currently_in_database.fetchone()[0] == 3, \
        "There should only be three records in the database."


def test_count_opted_out_records_query(notify_db_session):
    """
    If the value is opted out and the source_datetime
    is older than 24 hours, it should be selected.
    """

    with notify_db_session.engine.begin() as connection:
        setup_db(connection)

        connection.execute(COUNT_OPTED_OUT_RECORD_QUERY)

        count_opted_out_record = connection.execute(COUNT_OPTED_OUT_RECORD_QUERY)
        assert count_opted_out_record.fetchone()[0] == 1, \
            "The stored function should have removed one record that is opted out."


def test_remove_opted_out_records_query(notify_db_session):
    """
    If the difference between the current time and source_datetime
    is greater than 24 hours, the stored function should delete the records.
    """

    with notify_db_session.engine.begin() as connection:
        setup_db(connection)

        connection.execute(REMOVE_OPTED_OUT_RECORDS_QUERY)

        count_queryset = connection.execute(COUNT)
        assert count_queryset.fetchone()[0] == 2, \
            "The stored function should have two records remaining that are opted in."
