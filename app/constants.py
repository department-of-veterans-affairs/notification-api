"""Common constants."""

from datetime import timedelta
import os

from dotenv import load_dotenv

load_dotenv()

# Generic
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
DATE_FORMAT = '%Y-%m-%d'
HTTP_TIMEOUT = (3.05, 1) if os.getenv('NOTIFY_ENVIRONMENT') in ('production', 'staging') else (30, 30)

# Notification types
EMAIL_TYPE = 'email'
LETTER_TYPE = 'letter'
PUSH_TYPE = 'push'
SMS_TYPE = 'sms'
NOTIFICATION_TYPE = (EMAIL_TYPE, SMS_TYPE, LETTER_TYPE)

# Notification status
NOTIFICATION_CANCELLED = 'cancelled'
NOTIFICATION_CREATED = 'created'
NOTIFICATION_SENDING = 'sending'
NOTIFICATION_SENT = 'sent'
NOTIFICATION_DELIVERED = 'delivered'
NOTIFICATION_PENDING = 'pending'
NOTIFICATION_FAILED = 'failed'
NOTIFICATION_TEMPORARY_FAILURE = 'temporary-failure'
NOTIFICATION_PERMANENT_FAILURE = 'permanent-failure'
NOTIFICATION_PENDING_VIRUS_CHECK = 'pending-virus-check'
NOTIFICATION_VALIDATION_FAILED = 'validation-failed'
NOTIFICATION_VIRUS_SCAN_FAILED = 'virus-scan-failed'
NOTIFICATION_RETURNED_LETTER = 'returned-letter'
NOTIFICATION_CONTAINS_PII = 'pii-check-failed'

NOTIFICATION_STATUS_TYPES = (
    NOTIFICATION_CANCELLED,
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING,
    NOTIFICATION_FAILED,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_VALIDATION_FAILED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
    NOTIFICATION_RETURNED_LETTER,
    NOTIFICATION_CONTAINS_PII,
)

NOTIFICATION_STATUS_TYPES_COMPLETED = (
    NOTIFICATION_SENT,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_RETURNED_LETTER,
    NOTIFICATION_CANCELLED,
)

NOTIFICATION_STATUS_TYPES_FAILED = (
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_VALIDATION_FAILED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
    NOTIFICATION_RETURNED_LETTER,
    NOTIFICATION_CONTAINS_PII,
)

NOTIFICATION_STATUS_TYPES_BILLABLE_FOR_LETTERS = (
    NOTIFICATION_SENDING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_RETURNED_LETTER,
)

NOTIFICATION_STATUS_TYPES_BILLABLE = (
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_RETURNED_LETTER,
)

# VA Profile types
MOBILE_TYPE = 'mobile'

# Template
TEMPLATE_TYPES = (SMS_TYPE, EMAIL_TYPE, LETTER_TYPE)
TEMPLATE_PROCESS_NORMAL = 'normal'
TEMPLATE_PROCESS_PRIORITY = 'priority'
TEMPLATE_PROCESS_TYPE = (TEMPLATE_PROCESS_NORMAL, TEMPLATE_PROCESS_PRIORITY)

# Callbacks
DELIVERY_STATUS_CALLBACK_TYPE = 'delivery_status'
COMPLAINT_CALLBACK_TYPE = 'complaint'
INBOUND_SMS_CALLBACK_TYPE = 'inbound_sms'
# list for backwards compatibility
SERVICE_CALLBACK_TYPES = [DELIVERY_STATUS_CALLBACK_TYPE, COMPLAINT_CALLBACK_TYPE, INBOUND_SMS_CALLBACK_TYPE]
WEBHOOK_CHANNEL_TYPE = 'webhook'
QUEUE_CHANNEL_TYPE = 'queue'
CALLBACK_CHANNEL_TYPES = [WEBHOOK_CHANNEL_TYPE, QUEUE_CHANNEL_TYPE]

# Branding
BRANDING_ORG = 'org'
BRANDING_BOTH = 'both'
BRANDING_ORG_BANNER = 'org_banner'
BRANDING_NO_BRANDING = 'no_branding'
BRANDING_TYPES = (BRANDING_ORG, BRANDING_BOTH, BRANDING_ORG_BANNER, BRANDING_NO_BRANDING)

# Letters
DVLA_RESPONSE_STATUS_SENT = 'Sent'
FIRST_CLASS = 'first'
SECOND_CLASS = 'second'
POSTAGE_TYPES = (FIRST_CLASS, SECOND_CLASS)
RESOLVE_POSTAGE_FOR_FILE_NAME = {FIRST_CLASS: 1, SECOND_CLASS: 2}
NOTIFICATION_STATUS_LETTER_ACCEPTED = 'accepted'
NOTIFICATION_STATUS_LETTER_RECEIVED = 'received'

# Permissions
INTERNATIONAL_SMS_TYPE = 'international_sms'
INBOUND_SMS_TYPE = 'inbound_sms'
SCHEDULE_NOTIFICATIONS = 'schedule_notifications'
EMAIL_AUTH = 'email_auth'
LETTERS_AS_PDF = 'letters_as_pdf'
PRECOMPILED_LETTER = 'precompiled_letter'
UPLOAD_DOCUMENT = 'upload_document'
EDIT_FOLDER_PERMISSIONS = 'edit_folder_permissions'
UPLOAD_LETTERS = 'upload_letters'

SERVICE_PERMISSION_TYPES = (
    EMAIL_TYPE,
    SMS_TYPE,
    LETTER_TYPE,
    PUSH_TYPE,
    INTERNATIONAL_SMS_TYPE,
    INBOUND_SMS_TYPE,
    SCHEDULE_NOTIFICATIONS,
    EMAIL_AUTH,
    LETTERS_AS_PDF,
    UPLOAD_DOCUMENT,
    EDIT_FOLDER_PERMISSIONS,
    UPLOAD_LETTERS,
)


# Service Permissions
MANAGE_USERS = 'manage_users'
MANAGE_TEMPLATES = 'manage_templates'
EDIT_TEMPLATES = 'edit_templates'
MANAGE_SETTINGS = 'manage_settings'
SEND_TEXTS = 'send_texts'
SEND_EMAILS = 'send_emails'
SEND_LETTERS = 'send_letters'
MANAGE_API_KEYS = 'manage_api_keys'
PLATFORM_ADMIN = 'platform_admin'
VIEW_ACTIVITY = 'view_activity'

# Default permissions for a service
# Do not confuse this with DEFAULT_SERVICE_NOTIFICATION_PERMISSIONS for app/dao/services_dao.py.
DEFAULT_SERVICE_MANAGEMENT_PERMISSIONS = (
    MANAGE_USERS,
    MANAGE_TEMPLATES,
    MANAGE_SETTINGS,
    SEND_TEXTS,
    SEND_EMAILS,
    SEND_LETTERS,
    MANAGE_API_KEYS,
    VIEW_ACTIVITY,
)

# Do not confuse this with DEFAULT_SERVICE_MANAGEMENT_PERMISSIONS for app/dao/permissions_dao.py.
DEFAULT_SERVICE_NOTIFICATION_PERMISSIONS = (
    SMS_TYPE,
    EMAIL_TYPE,
    INTERNATIONAL_SMS_TYPE,
)

# List of permissions
PERMISSION_LIST = (
    MANAGE_USERS,
    MANAGE_TEMPLATES,
    EDIT_TEMPLATES,
    MANAGE_SETTINGS,
    SEND_TEXTS,
    SEND_EMAILS,
    SEND_LETTERS,
    MANAGE_API_KEYS,
    PLATFORM_ADMIN,
    VIEW_ACTIVITY,
)

# API key types
KEY_TYPE_NORMAL = 'normal'
KEY_TYPE_TEAM = 'team'
KEY_TYPE_TEST = 'test'

# User auth types
SMS_AUTH_TYPE = 'sms_auth'
EMAIL_AUTH_TYPE = 'email_auth'

# Orangaization
ORGANISATION_TYPES = ('other',)

# Deprecated but necessary
BRANDING_GOVUK = 'govuk'  # Deprecated outside migrations
INVITE_PENDING = 'pending'
INVITE_ACCEPTED = 'accepted'
INVITE_CANCELLED = 'cancelled'
INVITED_USER_STATUS_TYPES = (INVITE_PENDING, INVITE_ACCEPTED, INVITE_CANCELLED)

# Whitelist
WHITELIST_RECIPIENT_TYPE = (MOBILE_TYPE, EMAIL_TYPE)

# Providers
MMG_PROVIDER = 'mmg'
FIRETEXT_PROVIDER = 'firetext'
PINPOINT_PROVIDER = 'pinpoint'
SNS_PROVIDER = 'sns'
SES_PROVIDER = 'ses'
TWILIO_PROVIDER = 'twilio'

# Jobs
JOB_STATUS_PENDING = 'pending'
JOB_STATUS_IN_PROGRESS = 'in progress'
JOB_STATUS_FINISHED = 'finished'
JOB_STATUS_SENDING_LIMITS_EXCEEDED = 'sending limits exceeded'
JOB_STATUS_SCHEDULED = 'scheduled'
JOB_STATUS_CANCELLED = 'cancelled'
JOB_STATUS_READY_TO_SEND = 'ready to send'
JOB_STATUS_SENT_TO_DVLA = 'sent to dvla'
JOB_STATUS_ERROR = 'error'

JOB_STATUS_TYPES = (
    JOB_STATUS_PENDING,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_FINISHED,
    JOB_STATUS_SENDING_LIMITS_EXCEEDED,
    JOB_STATUS_SCHEDULED,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_READY_TO_SEND,
    JOB_STATUS_SENT_TO_DVLA,
    JOB_STATUS_ERROR,
)

# Status reasons
STATUS_REASON_RETRYABLE = (
    'Retryable - Notification is unable to be processed at this time. Replay the request to VA Notify.'
)
STATUS_REASON_INVALID_NUMBER = 'Undeliverable - Phone number is invalid'
STATUS_REASON_UNREACHABLE = 'Undeliverable - Individual unreachable'
STATUS_REASON_BLOCKED = 'Undeliverable - Individual or carrier has blocked the request'
STATUS_REASON_DECLINED = 'Undeliverable - Preferences declined in VA Profile'
STATUS_REASON_NO_CONTACT = 'Undeliverable - No VA Profile contact information'
STATUS_REASON_NO_PROFILE = 'Undeliverable - No VA Profile found in MPI'
STATUS_REASON_NO_ID_FOUND = 'Undeliverable - Identifier not found in MPI'
STATUS_REASON_DECEASED = 'Undeliverable - Individual is deceased'
STATUS_REASON_UNDELIVERABLE = 'Undeliverable - Unable to deliver'

# Carrier
CARRIER_SMS_MAX_RETRIES = 2
CARRIER_SMS_MAX_RETRY_WINDOW = timedelta(days=3)
