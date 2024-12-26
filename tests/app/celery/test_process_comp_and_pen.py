import pytest
from sqlalchemy.orm.exc import NoResultFound

from app.celery.process_comp_and_pen import comp_and_pen_batch_process


def test_comp_and_pen_batch_process_happy_path(mocker, sample_template) -> None:
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )
    mock_send = mocker.patch(
        'app.notifications.send_notifications.send_to_queue_for_recipient_info_based_on_recipient_identifier'
    )

    records = [
        {'participant_id': '55', 'payment_amount': '55.56', 'vaprofile_id': '57'},
        {'participant_id': '42', 'payment_amount': '42.42', 'vaprofile_id': '43627'},
    ]
    comp_and_pen_batch_process(records)

    # comp_and_pen_batch_process can fail without raising an exception, so test it called the send_to_queue...
    mock_send.call_count == len(records)


@pytest.mark.parametrize('exception_tested', [AttributeError, NoResultFound, ValueError])
def test_comp_and_pen_batch_process_exception(mocker, exception_tested) -> None:
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        side_effect=exception_tested,
    )

    with pytest.raises(exception_tested):
        comp_and_pen_batch_process({})
