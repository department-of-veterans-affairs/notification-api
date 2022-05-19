# Tutorial: Configuring a Lambda function to access Amazon RDS in an Amazon VPC
#   https://docs.aws.amazon.com/lambda/latest/dg/services-rds-tutorial.html
# https://www.psycopg.org/docs/usage.html

import logging
import os
import psycopg2
import sys
from http.client import ConnectionError, HTTPSConnection
from json import dumps


OPT_IN_OUT_QUERY = """SELECT va_profile_opt_in_out(%s, %s, %s, %s, %s);"""
NOTIFICATION_API_DB_URI = os.getenv("notification_api_db_uri")
VA_PROFILE_DOMAIN = "https://api.va.gov"
VA_PROFILE_PATH_BASE = "/communication-hub/communication/v1/status/changelog/"


if NOTIFICATION_API_DB_URI is None:
    logging.error("The database URI is not set.")
    sys.exit("Couldn't connect to the database.")


def make_connection():
    """
    Return a connection to the database, or return None.
    """

    connection = None

    # https://www.psycopg.org/docs/module.html#exceptions
    try:
        connection = psycopg2.connect(NOTIFICATION_API_DB_URI)
    except psycopg2.Warning as e:
        logging.warning(e)
    except psycopg2.Error as e:
        logging.exception(e)
        logging.error(e.pgcode)

    return connection


db_connection = None


def va_profile_opt_in_out_lambda_handler(event: dict, context) -> dict:
    """
    Use the event data to process veterans' opt-in/out requests as relayed by VA Profile.  The data fields
    are as specified in the "VA Profile Syncronization" document.  It looks like this:

        {
            txAuditId": "string",
            ...
            "bios": [
                {
                "txAuditId": "string",
                "sourceDate": "2022-03-07T19:37:59.320Z",
                "vaProfileId": 0,
                "communicationChannelId": 0,
                "communicationItemId": 0,
                "allowed": true,
                ...
                }
            ]
        }

    The lambda generally will be called by the Amazon API Gateway service.  Useful documentation:
        https://docs.aws.amazon.com/lambda/latest/dg/services-apigateway.html
        https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html
        https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-concepts.html#gettingstarted-concepts-event
    """

    if "txAuditId" not in event or "bios" not in event or not isinstance(event["bios"], list):
        # A required top level attribute is missing from the request.
        logging.debug(event)
        return { "statusCode": 400 }

    response = { "statusCode": 200 }

    put_request_body = {
        "txAuditId": event["txAuditId"],
        "bios": [],
    }

    problem_detected = False

    for record in event["bios"]:
        sufficient_for_put = True

        # Ensure that the record has the necessary fields to PUT to VA Profile.
        try:
            if record.get("txAuditId", '') != event["txAuditId"]:
                raise KeyError

            put_record = {
                "vaProfileId": record["vaProfileId"],
                "communicationChannelId": record["communicationChannelId"],
                "communicationItemId": record["communicationItemId"],
            }
        except KeyError:
            problem_detected = True
            sufficient_for_put = False

        # Process the possible preference update.
        try:
            params = (                             # Stored function parameters:
                record["VaProfileId"],             #     _va_profile_id
                record["CommunicationItemId"],     #     _communication_item_id
                record["CommunicationChannelId"],  #     _communication_channel_name
                record["allowed"],                 #     _allowed
                record["sourceDate"],              #     _source_datetime
            )

            if db_connection is None or db_connection.status != 0:
                # Attempt to (re-)establish a database connection
                db_connection = make_connection()

            if db_connection is None:
                raise RuntimeError("No database connection.")

            # Execute the stored function.
            with db_connection.cursor() as c:
                put_record["status"] = "COMPLETED_SUCCESS" if c.execute(OPT_IN_OUT_QUERY, params) else "COMPLETED_NOOP"
        except KeyError as e:
            # Bad Request
            response["statusCode"] = 400
            put_record["status"] = "COMPLETED_FAILURE"
            problem_detected = True
            logging.exception(e)
        except Exception as e:
            # Internal Server Error.  Prefer to return 400 if multiple records raise exceptions.
            if response["statusCode"] != 400:
                response["statusCode"] = 500
            put_record["status"] = "COMPLETED_FAILURE"
            problem_detected = True
            logging.exception(e)

        if sufficient_for_put:
            # Include the status of processing this record in the PUT to VA Profile.
            put_request_body["bios"].append(put_record)

    if response["statusCode"] != 200 or problem_detected:
        logging.debug(event)

    if len(put_request_body["bios"]) > 0 and VA_PROFILE_DOMAIN is not None:
        try:
            # Make a PUT request to VA Profile.
            https_connection = HTTPSConnection(VA_PROFILE_DOMAIN)
            https_connection.request(
                "PUT",
                VA_PROFILE_PATH_BASE + event["txAuditId"],
                dumps(put_request_body),
                { "Content-Type": "application/json" }
            )
            put_response = https_connection.response()
            if put_response.status != 200:
                logging.info("VA Profile responded with %d.", put_response.status)
        except ConnectionError as e:
            logging.error("The PUT request to VA Profile failed.")
            logging.exception(e)
        finally:
            https_connection.close()

    return response
