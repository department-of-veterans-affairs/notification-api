import logging
import time

from celery import Celery, Task
from celery.signals import task_prerun, task_postrun, worker_process_shutdown, worker_shutting_down, worker_process_init
from flask import current_app


@worker_process_init.connect
def pool_worker_started(
    *args,
    **kwargs,
):
    current_app.logger.info('Pool worker started')


@worker_process_shutdown.connect
def pool_worker_process_shutdown(
    pid,
    exitcode,
    *args,
    **kwargs,
):
    current_app.logger.info('Pool worker shutdown: pid = %s, exitcode = %s', pid, exitcode)


@worker_shutting_down.connect
def main_proc_graceful_stop(
    signal,
    how,
    exitcode,
    *args,
    **kwargs,
):
    current_app.logger.info(
        'Main process worker graceful stop: signal = %s, how = %s, exitcode = %s', signal, how, exitcode
    )


def make_task(app):
    class NotifyTask(Task):
        abstract = True
        start = None

        def on_success(
            self,
            retval,
            task_id,
            args,
            kwargs,
        ):
            elapsed_time = time.time() - self.start
            app.logger.info('celery task success: %s took %.4f seconds', self.name, elapsed_time)

        def on_failure(
            self,
            exc,
            task_id,
            args,
            kwargs,
            einfo,
        ):
            elapsed_time = time.time() - self.start

            # ensure task will log exceptions to correct handlers
            app.logger.exception('celery task failure: %s took %.4f seconds', self.name, elapsed_time)
            super().on_failure(exc, task_id, args, kwargs, einfo)

        def __call__(
            self,
            *args,
            **kwargs,
        ):
            # ensure task has flask context to access config, logger, etc
            with app.app_context():
                self.start = time.time()
                return super().__call__(*args, **kwargs)

    return NotifyTask


class NotifyCelery(Celery):
    def init_app(
        self,
        app,
    ):
        super().__init__(
            app.import_name,
            broker=app.config['CELERY_SETTINGS']['broker_url'],
            task_cls=make_task(app),
        )

        self.conf.update(app.config['CELERY_SETTINGS'])


class CeleryRequestIdFilter(logging.Filter):
    def __init__(self, request_id: str, name=''):
        self.request_id = request_id
        super().__init__(name)

    def filter(self, record):
        record.requestId = self.request_id
        return record


@task_prerun.connect
def add_id_to_logger(task_id, task, *args, **kwargs):
    request_id = kwargs.get('notification_id', task_id)
    current_app.logger.addFilter(CeleryRequestIdFilter(request_id, f'celery-{request_id}'))


@task_postrun.connect
def id_cleanup_logger(task_id, task, *args, **kwargs):
    request_id = kwargs.get('notification_id', task_id)
    for filter in current_app.logger.filters:
        if filter.name == f'celery-{request_id}':
            current_app.logger.removeFilter(filter)
