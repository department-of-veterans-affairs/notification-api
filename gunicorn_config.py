import os
import sys
import traceback
from pprint import pprint
import inspect

workers = 4
worker_class = "eventlet"
worker_connections = 256
bind = "0.0.0.0:{}".format(os.getenv("PORT"))
accesslog = '-'


def on_starting(server):
    server.log.info("Starting Notifications API")


def worker_abort(worker):
    worker.log.info("worker received ABORT {}".format(worker.pid))
    for threadId, stack in sys._current_frames().items():
        worker.log.error(''.join(traceback.format_stack(stack)))


def on_exit(server):
    server.log.info("Stopping Notifications API")


def worker_int(worker):
    worker.log.info("worker: received SIGINT {}".format(worker.pid))


def post_request(worker, req, environ, resp):
    print("----start of worker object ----")
    pprint(inspect.getmembers(worker))
    print("----end of worker object ----")
    print("----start of req object ----")
    pprint(inspect.getmembers(req))
    print("----end of req object ----")
    print("----start of resp object ----")
    pprint(inspect.getmembers(resp))
    print("----end of resp object ----")
