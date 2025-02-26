import itertools

from flask import current_app

from app import db
from app.history_meta import create_history
from functools import wraps
from contextlib import contextmanager
from sqlalchemy.orm import scoped_session, sessionmaker


def transactional(func):
    """
    This is a decorator for creating a transactional database operation.
    """

    @wraps(func)
    def commit_or_rollback(
        *args,
        **kwargs,
    ):
        try:
            res = func(*args, **kwargs)
            db.session.commit()
            return res
        except Exception as e:
            current_app.logger.exception('Encountered transaction error: %s', type(e).__name__)
            db.session.rollback()
            raise

    return commit_or_rollback


class VersionOptions:
    def __init__(
        self,
        model_class,
        history_class=None,
        must_write_history=True,
    ):
        self.model_class = model_class
        self.history_class = history_class
        self.must_write_history = must_write_history


def version_class(*version_options):
    if len(version_options) == 1 and not isinstance(version_options[0], VersionOptions):
        version_options = (VersionOptions(version_options[0]),)

    def versioned(func):
        @wraps(func)
        def record_version(
            *args,
            **kwargs,
        ):
            func(*args, **kwargs)

            session_objects = []

            for version_option in version_options:
                tmp_session_objects = [
                    (session_object, version_option.history_class)
                    for session_object in itertools.chain(db.session.new, db.session.dirty)
                    if isinstance(session_object, version_option.model_class)
                ]

                if tmp_session_objects == [] and version_option.must_write_history:
                    raise RuntimeError(
                        (
                            "Can't record history for {} "
                            '(something in your code has casued the database to '
                            "flush the session early so there's nothing to "
                            'copy into the history table)'
                        ).format(version_option.model_class.__name__)
                    )

                session_objects += tmp_session_objects

            for session_object, history_class in session_objects:
                db.session.add(create_history(session_object, history_cls=history_class))

        return record_version

    return versioned


def dao_rollback():
    db.session.rollback()


@contextmanager
def get_reader_session():
    """
    This context manager is used to abstract the connection to the read-only database engine
    in order to execute read queries. By using a scoped session, it ensures that the session
    is thread-local and can be reused if needed. It ensures proper handling of the session's
    lifecycle by closing it when the context is exited.

    Yields:
        session (scoped_session): A session connected to the read-only database engine.

    Example Usage:
        with get_reader_session() as session:
            query = select(Service).where(Service.id == service_id)
            result = session.scalars(query).one()
    """
    engine = db.engines['read-db']
    session = scoped_session(sessionmaker(bind=engine))
    try:
        yield session
    finally:
        session.close()
