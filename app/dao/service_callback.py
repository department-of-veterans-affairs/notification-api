from notifications_utils.statsd_decorators import statsd
from sqlalchemy.orm.exc import NoResultFound
from app.models import (ServiceCallback)


@statsd(namespace="dao")
def dao_get_callback_include_payload_status(service_id, service_callback_type):

    # Throw error is you return 0 or more than 1 row
    try:
        row = ServiceCallback\
            .query.filter_by(service_id=service_id)\
            .filter_by(callback_type=service_callback_type) \
            .one()
    except NoResultFound as e:
        raise e

    # Attempt to get the include payload property
    try:
        include_provider_payload = row.include_provider_payload
    except Exception as e:
        raise e

    if not isinstance(include_provider_payload, bool):
        raise TypeError

    return include_provider_payload
