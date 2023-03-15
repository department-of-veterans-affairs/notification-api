import functools
import string
import uuid
from datetime import (
    datetime,
    timedelta,
)

from botocore.exceptions import ClientError
from flask import current_app
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES
from notifications_utils.recipients import (
    validate_and_format_email_address,
    InvalidEmailError,
    try_validate_and_format_phone_number
)
from notifications_utils.statsd_decorators import statsd
from notifications_utils.timezones import convert_local_timezone_to_utc, convert_utc_to_local_timezone
from sqlalchemy import (desc, func, asc)
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import functions
from sqlalchemy.sql.expression import case
from sqlalchemy.dialects.postgresql import insert
from werkzeug.datastructures import MultiDict

from app import db, create_uuid
from app.aws.s3 import remove_s3_object, get_s3_bucket_objects
from app.dao.dao_utils import transactional
from app.errors import InvalidRequest
from app.feature_flags import is_feature_enabled, FeatureFlag
from app.letters.utils import LETTERS_PDF_FILE_LOCATION_STRUCTURE
from app.models import (ServiceCallback)
from app.utils import get_local_timezone_midnight_in_utc
from app.utils import midnight_n_days_ago, escape_special_characters


@statsd(namespace="dao")
def dao_get_include_status(service_id):
    retval = True
    include_provider_payload = ServiceCallback\
        .query(ServiceCallback.include_provider_payload)\
        .filter(ServiceCallback.service_id == service_id)\
        .first()

    if not include_provider_payload:
        retval = False

    return retval

