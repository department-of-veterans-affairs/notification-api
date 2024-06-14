from uuid import UUID

import boto3
from boto3.dynamodb.conditions import Attr
from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.models import (
    SMS_TYPE,
    Service,
    Template,
)
from app.notifications.send_notifications import send_notification_bypass_route
from app.va.identifier import IdentifierType


class CompPenMsgHelper:
    """
    This class is a collection of helper methods to facilitate the delivery of schedule Comp and Pen notifications.
    When initialized it establishes a connection to the dynamodb table with the given name.
    """

    def __init__(self, dynamodb_table_name: str) -> None:
        """"""
        # this is the agreed upon message per 2 minute limit
        self.messages_per_min = 3000

        # connect to dynamodb table
        dynamodb = boto3.resource('dynamodb')
        self.table = dynamodb.Table(dynamodb_table_name)

    def get_dynamodb_comp_pen_messages(
        self,
        message_limit: int,
    ) -> list:
        """
        Helper function to get the Comp and Pen data from our dynamodb cache table.  Items should be returned if all of
        these attribute conditions are met:
            1) is_processed is not set or False
            2) has_duplicate_mappings is not set or False
            3) payment_id is not equal to -1 (placeholder value)
            4) paymentAmount exists

        :param table: the dynamodb table to grab the data from
        :param message_limit: the number of rows to search at a time and the max number of items that should be returned
        :return: a list of entries from the table that have not been processed yet

        https://boto3.amazonaws.com/v1/documentation/api/latest/guide/dynamodb.html#querying-and-scanning
        """

        is_processed_index = 'is-processed-index'

        filters = (
            Attr('payment_id').exists()
            & Attr('payment_id').ne(-1)
            & Attr('paymentAmount').exists()
            & Attr('has_duplicate_mappings').ne(True)
        )

        results = self.table.scan(FilterExpression=filters, Limit=message_limit, IndexName=is_processed_index)
        items: list = results.get('Items')

        if items is None:
            current_app.logger.critical(
                'Error in _get_dynamodb_comp_pen_messages trying to read "Items" from dynamodb table scan result. '
                'Returned results does not include "Items" - results: %s',
                results,
            )
            items = []

        # Keep getting items from the table until we have the number we want to send, or run out of items
        while 'LastEvaluatedKey' in results and len(items) < message_limit:
            results = self.table.scan(
                FilterExpression=filters,
                Limit=message_limit,
                IndexName=is_processed_index,
                ExclusiveStartKey=results['LastEvaluatedKey'],
            )

            items.extend(results['Items'])

        return items[:message_limit]

    def remove_dynamo_item_is_processed(self, comp_and_pen_messages: list) -> None:
        """
        Remove the 'is_processed' key from each item in the provided list and update the entries in the DynamoDB table.

        Args:
            comp_and_pen_messages (list): A list of dictionaries, where each dictionary contains the data for an item to
                                        be updated in the DynamoDB table. Each dictionary should at least contain
                                        'participant_id' and 'payment_id' keys, as well as the 'is_processed' key to be
                                        removed.

        Raises:
            Exception: If an error occurs during the update of any item in the DynamoDB table, the exception is logged
                    with critical severity, and then re-raised.
        """
        # send messages and update entries in dynamodb table
        with self.table.batch_writer() as batch:
            for item in comp_and_pen_messages:
                participant_id = item.get('participant_id')
                payment_id = item.get('payment_id')

                item.pop('is_processed', None)

                # update dynamodb entries
                try:
                    batch.put_item(Item=item)
                    current_app.logger.info(
                        'updated_item from dynamodb ("is_processed" should no longer exist): %s', item
                    )
                except Exception as e:
                    current_app.logger.critical(
                        'Exception attempting to update item in dynamodb with participant_id: %s and payment_id: %s - '
                        'exception_type: %s exception_message: %s',
                        participant_id,
                        payment_id,
                        type(e),
                        e,
                    )
                    raise

    def get_setup_data(
        self,
        service_id: str,
        template_id: str,
        sms_sender_id: str,
    ) -> tuple[Service, Template, str] | None:
        try:
            service: Service = dao_fetch_service_by_id(service_id)
            template: Template = dao_get_template_by_id(template_id)
        except NoResultFound as e:
            current_app.logger.error(
                'No results found in task send_scheduled_comp_and_pen_sms attempting to lookup service or template. Exiting'
                ' - exception: %s',
                e,
            )
            raise
        except Exception as e:
            current_app.logger.critical(
                'Error in task send_scheduled_comp_and_pen_sms attempting to lookup service or template Exiting - '
                'exception: %s',
                e,
            )
            raise

        try:
            # If this line doesn't raise ValueError, the value is a valid UUID.
            sms_sender_id = UUID(sms_sender_id)
            current_app.logger.info('Using the SMS sender ID specified in SSM Parameter store.')
        except ValueError:
            sms_sender_id = service.get_default_sms_sender_id()
            current_app.logger.info("Using the service default ServiceSmsSender's ID.")

        return service, template, str(sms_sender_id)

    def send_scheduled_sms(
        self,
        service: Service,
        template: Template,
        sms_sender_id: str,
        comp_and_pen_messages: list,
        perf_to_number: str,
    ) -> None:
        for item in comp_and_pen_messages:
            vaprofile_id = str(item.get('vaprofile_id'))
            participant_id = item.get('participant_id')
            payment_id = item.get('payment_id')
            payment_amount = str(item.get('paymentAmount'))

            current_app.logger.info(
                'sending - item from dynamodb - vaprofile_id: %s | participant_id: %s | payment_id: %s',
                vaprofile_id,
                participant_id,
                payment_id,
            )

            # Use perf_to_number as the recipient if available. Otherwise, use vaprofile_id as recipient_item.
            recipient = perf_to_number
            recipient_item = (
                None
                if perf_to_number is not None
                else {
                    'id_type': IdentifierType.VA_PROFILE_ID.value,
                    'id_value': vaprofile_id,
                }
            )

            try:
                # call generic method to send messages
                send_notification_bypass_route(
                    service=service,
                    template=template,
                    notification_type=SMS_TYPE,
                    personalisation={'paymentAmount': payment_amount},
                    sms_sender_id=sms_sender_id,
                    recipient=recipient,
                    recipient_item=recipient_item,
                )
            except Exception as e:
                current_app.logger.critical(
                    'Error attempting to send Comp and Pen notification with send_scheduled_comp_and_pen_sms | item from '
                    'dynamodb - vaprofile_id: %s | participant_id: %s | payment_id: %s | exception_type: %s - '
                    'exception: %s',
                    vaprofile_id,
                    participant_id,
                    payment_id,
                    type(e),
                    e,
                )
            else:
                if perf_to_number is not None:
                    current_app.logger.info(
                        'Notification sent using Perf simulated number %s instead of vaprofile_id', perf_to_number
                    )

                current_app.logger.info(
                    'Notification sent to queue for item from dynamodb - vaprofile_id: %s | participant_id: %s | '
                    'payment_id: %s',
                    vaprofile_id,
                    participant_id,
                    payment_id,
                )
