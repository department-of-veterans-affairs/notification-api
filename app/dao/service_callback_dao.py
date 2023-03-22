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
            .filter_by(include_provider_payload=True) \
            .one()

        include_provider_payload = row.include_provider_payload

    except (NoResultFound, AttributeError) as e:
        raise e

    # make sure include_provider_payload is boolean
    if not isinstance(include_provider_payload, bool):
        raise TypeError

    return include_provider_payload
