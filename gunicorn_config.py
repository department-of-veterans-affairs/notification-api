import os
import sys
import traceback

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


def post_fork(server, worker):
    server.log.info("Gunicorn Worker spawned (pid: %s)", worker.pid)


def pre_fork(server, worker):
    server.log.info("Gunicorn Worker exiting (pid: %s)", worker.pid)


def when_ready(server):
    server.log.info("Gunicorn Server is ready. Spawning workers")


def pre_request(worker, req):
    worker.log.info(f"Gunicorn Worker is about to process request: {worker.pid}")


def post_request(worker, req, environ, resp):
    worker.log.info(f"Gunicorn Worker finished processing request: {worker.pid}")
