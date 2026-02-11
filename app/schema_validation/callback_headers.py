"""Validation for custom callback headers.

Validates header names and values per ADR-001 constraints:
- Max 5 headers
- Header names: 1-256 chars, RFC 7230 token characters only
- Header values: 1-1024 chars, strings only
- Blocked header names and prefixes to prevent security issues
"""

import re

# RFC 7230 token characters: A-Z a-z 0-9 !#$%&'*+-.^_`|~
_RFC7230_TOKEN_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~]+$")

# Reject control characters in header values (defense-in-depth against CRLF injection)
_HEADER_VALUE_BAD_CHARS_RE = re.compile(r'[\r\n\x00]')

MAX_HEADER_COUNT = 5
MAX_HEADER_NAME_LENGTH = 256
MAX_HEADER_VALUE_LENGTH = 1024

BLOCKED_HEADER_NAMES = frozenset(
    name.lower()
    for name in (
        'authorization',
        'content-type',
        'content-length',
        'transfer-encoding',
        'connection',
        'host',
        'cookie',
    )
)

BLOCKED_HEADER_PREFIXES = (
    'x-forwarded-',
    'x-real-',
    'x-amz-',
    'x-envoy-',
)

# Additional blocked names for notification-level callbacks
NOTIFICATION_LEVEL_BLOCKED_NAMES = frozenset(
    name.lower()
    for name in (
        'x-enp-signature',
    )
)


def validate_callback_headers(callback_headers, is_notification_level=False):
    """Validate callback_headers dict and return a list of error messages.

    Args:
        callback_headers: The callback_headers value to validate.
        is_notification_level: If True, also blocks 'x-enp-signature'.

    Returns:
        list[str]: A list of validation error messages. Empty if valid.
    """
    errors = []

    if not isinstance(callback_headers, dict):
        return ['callback_headers must be a dictionary']

    # Empty dict is valid (treated as absent)
    if not callback_headers:
        return []

    if len(callback_headers) > MAX_HEADER_COUNT:
        errors.append(f'callback_headers cannot contain more than {MAX_HEADER_COUNT} headers')

    blocked_names = BLOCKED_HEADER_NAMES
    if is_notification_level:
        blocked_names = blocked_names | NOTIFICATION_LEVEL_BLOCKED_NAMES

    for name, value in callback_headers.items():
        if not isinstance(name, str):
            errors.append(f'Header name must be a string, got {type(name).__name__}')
            continue

        if not isinstance(value, str):
            errors.append(f'Header value for "{name}" must be a string, got {type(value).__name__}')
            continue

        # Name length
        if len(name) < 1:
            errors.append('Header name cannot be empty')
            continue

        if len(name) > MAX_HEADER_NAME_LENGTH:
            errors.append(f'Header name "{name[:50]}..." exceeds maximum length of {MAX_HEADER_NAME_LENGTH}')

        # Name character set
        if not _RFC7230_TOKEN_RE.match(name):
            errors.append(f'Header name "{name}" contains invalid characters (must be RFC 7230 token characters)')

        # Value length
        if len(value) < 1:
            errors.append(f'Header value for "{name}" cannot be empty')

        if len(value) > MAX_HEADER_VALUE_LENGTH:
            errors.append(f'Header value for "{name}" exceeds maximum length of {MAX_HEADER_VALUE_LENGTH}')

        # Value character safety (defense-in-depth against CRLF injection)
        if _HEADER_VALUE_BAD_CHARS_RE.search(value):
            errors.append(f'Header value for "{name}" contains invalid control characters')

        # Blocked names
        name_lower = name.lower()
        if name_lower in blocked_names:
            errors.append(f'Header name "{name}" is not allowed')

        # Blocked prefixes
        for prefix in BLOCKED_HEADER_PREFIXES:
            if name_lower.startswith(prefix):
                errors.append(f'Header name "{name}" uses a blocked prefix "{prefix}"')
                break

    return errors


def merge_callback_headers(system_headers, custom_headers):
    """Merge custom headers into system headers with defense-in-depth filtering.

    Custom headers that conflict with blocked names/prefixes are silently dropped
    as a defense-in-depth measure (validation should have caught them earlier).

    Args:
        system_headers: dict of system headers (Content-Type, Authorization, etc.)
        custom_headers: dict of custom headers to merge, or None.

    Returns:
        dict: Merged headers with system headers taking precedence.
    """
    if not custom_headers:
        return dict(system_headers)

    merged = dict(system_headers)

    # Collect lowercase system header names to prevent override
    system_names_lower = {k.lower() for k in system_headers}

    for name, value in custom_headers.items():
        name_lower = name.lower()

        # Defense-in-depth: skip blocked headers even if validation missed them
        if name_lower in BLOCKED_HEADER_NAMES:
            continue

        if any(name_lower.startswith(prefix) for prefix in BLOCKED_HEADER_PREFIXES):
            continue

        # Prevent overriding system headers
        if name_lower in system_names_lower:
            continue

        merged[name] = value

    return merged
