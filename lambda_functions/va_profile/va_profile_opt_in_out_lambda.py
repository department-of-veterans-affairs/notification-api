# Tutorial: Configuring a Lambda function to access Amazon RDS in an Amazon VPC
#   https://docs.aws.amazon.com/lambda/latest/dg/services-rds-tutorial.html
# https://www.psycopg.org/docs/usage.html

import logging
import os
import psycopg2
import sys

OPT_IN_OUT_QUERY = """SELECT va_profile_opt_in_out(%s, %s, %s, %s, %s);"""
NOTIFICATION_API_DB_URI = os.getenv("notification_api_db_uri")

if NOTIFICATION_API_DB_URI is None:
    logging.error("The database URI is not set.")
    sys.exit("Couldn't connect to the database.")

# https://www.psycopg.org/docs/module.html#exceptions
try:
    connection = psycopg2.connect(NOTIFICATION_API_DB_URI)
except psycopg2.Warning as e:
    logging.warning(e)
except psycopg2.Error as e:
    logging.exception(e)

    # https://www.psycopg.org/docs/errorcodes.html
    sys.exit(e.pgcode)


def va_profile_opt_in_out_lambda_handler(event: dict, context) -> dict:
    """
    Use the event data to process veterans' opt-in/out requests as relayed by VA Profile.  The data fields
    are as specified in the "VA Profile Syncronization" document.
        https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html
    """

    logging.debug(event)

    response = {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": "Success",
    }

    try:
        params = (                                    # Stored function parameters:
            event["bios"]["VaProfileId"],             #     _va_profile_id
            event["bios"]["CommunicationItemId"],     #     _communication_item_id
            event["bios"]["CommunicationChannelId"],  #     _communication_channel_name
            event["bios"]["allowed"],                 #     _allowed
            event["bios"]["sourceDate"],              #     _source_datetime
        )

        # Execute the appropriate stored function.
        with connection.cursor() as c:
            c.execute(OPT_IN_OUT_QUERY, params)
    except Exception as e:
        logging.exception(e)
        response["body"] = str(e)

        # Bad Request (400) or Internal Server Error (500)
        response["statusCode"] = 400 if isinstance(e, KeyError) else 500

    # TODO - PUT back to VA Profile

    return response
