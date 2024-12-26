from flask import current_app

from app import notify_celery
from notifications_utils.statsd_decorators import statsd

@notify_celery.task(name='comp-and-pen-batch-process')
@statsd(namespace='tasks')
def comp_and_pen_batch_process(records: list[dict[str, int | float]]) -> None:
    current_app.logger.info(f'comp_and_pen_batch_process records: {records}')
