import pytest

from app.schema_validation.callback_headers import (
    BLOCKED_HEADER_NAMES,
    BLOCKED_HEADER_PREFIXES,
    MAX_HEADER_COUNT,
    MAX_HEADER_NAME_LENGTH,
    MAX_HEADER_VALUE_LENGTH,
    NOTIFICATION_LEVEL_BLOCKED_NAMES,
    merge_callback_headers,
    validate_callback_headers,
)


# ── validate_callback_headers: valid inputs ─────────────────────────────────


class TestValidateCallbackHeadersValid:
    def test_single_valid_header(self):
        assert validate_callback_headers({'X-Custom': 'value'}) == []

    def test_multiple_valid_headers(self):
        headers = {f'X-Header-{i}': f'value-{i}' for i in range(MAX_HEADER_COUNT)}
        assert validate_callback_headers(headers) == []

    def test_empty_dict_is_valid(self):
        assert validate_callback_headers({}) == []

    @pytest.mark.parametrize(
        'name',
        [
            'X-Custom',
            'Accept',
            'x-my-header',
            "!#$%&'*+-.^_`|~",
            'A',
            'a' * MAX_HEADER_NAME_LENGTH,
        ],
        ids=[
            'mixed-case',
            'simple',
            'lowercase-dashed',
            'all-rfc7230-special-chars',
            'single-char',
            'max-length',
        ],
    )
    def test_valid_header_names(self, name):
        assert validate_callback_headers({name: 'value'}) == []

    def test_valid_header_value_at_max_length(self):
        assert validate_callback_headers({'X-Custom': 'v' * MAX_HEADER_VALUE_LENGTH}) == []


# ── validate_callback_headers: type errors ───────────────────────────────────


class TestValidateCallbackHeadersTypeErrors:
    @pytest.mark.parametrize(
        'bad_input',
        [None, 42, 'string', ['a', 'b'], True],
        ids=['none', 'int', 'str', 'list', 'bool'],
    )
    def test_non_dict_rejected(self, bad_input):
        errors = validate_callback_headers(bad_input)
        assert errors == ['callback_headers must be a dictionary']

    @pytest.mark.parametrize(
        'bad_value,type_name',
        [(123, 'int'), (True, 'bool'), (None, 'NoneType'), (['a'], 'list'), ({'k': 'v'}, 'dict')],
        ids=['int', 'bool', 'none', 'list', 'dict'],
    )
    def test_header_value_must_be_string(self, bad_value, type_name):
        errors = validate_callback_headers({'X-Custom': bad_value})
        assert len(errors) == 1
        assert type_name in errors[0]

    def test_header_name_must_be_string(self):
        errors = validate_callback_headers({42: 'value'})
        assert len(errors) == 1
        assert 'must be a string' in errors[0]


# ── validate_callback_headers: count limit ───────────────────────────────────


class TestValidateCallbackHeadersCount:
    def test_at_max_count_is_valid(self):
        headers = {f'X-H-{i}': 'v' for i in range(MAX_HEADER_COUNT)}
        assert validate_callback_headers(headers) == []

    def test_exceeds_max_count(self):
        headers = {f'X-H-{i}': 'v' for i in range(MAX_HEADER_COUNT + 1)}
        errors = validate_callback_headers(headers)
        assert any(str(MAX_HEADER_COUNT) in e for e in errors)


# ── validate_callback_headers: header name validation ────────────────────────


class TestValidateCallbackHeadersName:
    def test_empty_header_name_key(self):
        errors = validate_callback_headers({'': 'value'})
        assert any('cannot be empty' in e for e in errors)

    def test_header_name_exceeds_max_length(self):
        long_name = 'X' * (MAX_HEADER_NAME_LENGTH + 1)
        errors = validate_callback_headers({long_name: 'value'})
        assert any('exceeds maximum length' in e for e in errors)

    @pytest.mark.parametrize(
        'bad_char',
        [' ', '\t', '(', ')', '<', '>', '@', ',', ';', ':', '\\', '"', '/', '[', ']', '?', '=', '{', '}'],
        ids=lambda c: f'char-{ord(c):02x}',
    )
    def test_invalid_header_name_characters(self, bad_char):
        errors = validate_callback_headers({f'X{bad_char}Header': 'value'})
        assert any('invalid characters' in e for e in errors)


# ── validate_callback_headers: header value validation ───────────────────────


class TestValidateCallbackHeadersValue:
    def test_empty_value(self):
        errors = validate_callback_headers({'X-Custom': ''})
        assert any('cannot be empty' in e for e in errors)

    def test_value_exceeds_max_length(self):
        errors = validate_callback_headers({'X-Custom': 'v' * (MAX_HEADER_VALUE_LENGTH + 1)})
        assert any('exceeds maximum length' in e for e in errors)

    @pytest.mark.parametrize(
        'bad_value',
        [
            'value\r\nX-Injected: evil',
            'value\ninjected',
            'value\rinjected',
            'value\x00null',
        ],
    )
    def test_value_with_control_characters_rejected(self, bad_value):
        errors = validate_callback_headers({'X-Custom': bad_value})
        assert any('invalid control characters' in e for e in errors)

    def test_value_at_max_length_accepted(self):
        errors = validate_callback_headers({'X-Custom': 'v' * MAX_HEADER_VALUE_LENGTH})
        assert errors == []


# ── validate_callback_headers: blocked header names ──────────────────────────


class TestValidateCallbackHeadersBlockedNames:
    @pytest.mark.parametrize('blocked_name', sorted(BLOCKED_HEADER_NAMES))
    def test_blocked_header_name_lowercase(self, blocked_name):
        errors = validate_callback_headers({blocked_name: 'value'})
        assert any('is not allowed' in e for e in errors)

    @pytest.mark.parametrize('blocked_name', sorted(BLOCKED_HEADER_NAMES))
    def test_blocked_header_name_mixed_case(self, blocked_name):
        errors = validate_callback_headers({blocked_name.upper(): 'value'})
        assert any('is not allowed' in e for e in errors)


# ── validate_callback_headers: blocked header prefixes ───────────────────────


class TestValidateCallbackHeadersBlockedPrefixes:
    @pytest.mark.parametrize('prefix', BLOCKED_HEADER_PREFIXES)
    def test_blocked_prefix(self, prefix):
        errors = validate_callback_headers({f'{prefix}something': 'value'})
        assert any('blocked prefix' in e for e in errors)

    @pytest.mark.parametrize('prefix', BLOCKED_HEADER_PREFIXES)
    def test_blocked_prefix_case_insensitive(self, prefix):
        errors = validate_callback_headers({f'{prefix.upper()}something': 'value'})
        assert any('blocked prefix' in e for e in errors)


# ── validate_callback_headers: notification-level ────────────────────────────


class TestValidateCallbackHeadersNotificationLevel:
    @pytest.mark.parametrize('blocked_name', sorted(NOTIFICATION_LEVEL_BLOCKED_NAMES))
    def test_notification_level_blocked_names(self, blocked_name):
        errors = validate_callback_headers({blocked_name: 'value'}, is_notification_level=True)
        assert any('is not allowed' in e for e in errors)

    @pytest.mark.parametrize('blocked_name', sorted(NOTIFICATION_LEVEL_BLOCKED_NAMES))
    def test_notification_level_blocked_names_allowed_at_service_level(self, blocked_name):
        errors = validate_callback_headers({blocked_name: 'value'}, is_notification_level=False)
        # Should NOT be blocked at service level
        assert not any('is not allowed' in e for e in errors)


# ── validate_callback_headers: multiple errors ──────────────────────────────


class TestValidateCallbackHeadersMultipleErrors:
    def test_multiple_errors_reported_together(self):
        headers = {
            'authorization': 'blocked-name',
            'X Bad Name': 'has space',
            'X-Good': '',
        }
        errors = validate_callback_headers(headers)
        assert len(errors) >= 3

    def test_count_error_combined_with_name_errors(self):
        headers = {f'authorization{i}': 'v' for i in range(MAX_HEADER_COUNT + 1)}
        # Should get at least the count error
        errors = validate_callback_headers(headers)
        assert any(str(MAX_HEADER_COUNT) in e for e in errors)


# ── merge_callback_headers ───────────────────────────────────────────────────


class TestMergeCallbackHeaders:
    def test_no_custom_headers_returns_copy_of_system(self):
        system = {'Content-Type': 'application/json'}
        result = merge_callback_headers(system, None)
        assert result == system
        assert result is not system

    def test_empty_custom_headers_returns_copy_of_system(self):
        system = {'Content-Type': 'application/json'}
        result = merge_callback_headers(system, {})
        assert result == system
        assert result is not system

    def test_valid_custom_headers_merged(self):
        system = {'Content-Type': 'application/json'}
        custom = {'X-Custom': 'my-value', 'X-Another': 'other'}
        result = merge_callback_headers(system, custom)
        assert result == {
            'Content-Type': 'application/json',
            'X-Custom': 'my-value',
            'X-Another': 'other',
        }

    def test_does_not_mutate_system_headers(self):
        system = {'Content-Type': 'application/json'}
        system_copy = dict(system)
        merge_callback_headers(system, {'X-Custom': 'value'})
        assert system == system_copy

    def test_does_not_mutate_custom_headers(self):
        custom = {'X-Custom': 'value'}
        custom_copy = dict(custom)
        merge_callback_headers({'Content-Type': 'application/json'}, custom)
        assert custom == custom_copy

    def test_system_headers_not_overridden(self):
        system = {'Content-Type': 'application/json'}
        custom = {'content-type': 'text/plain'}
        result = merge_callback_headers(system, custom)
        assert result['Content-Type'] == 'application/json'
        assert len(result) == 1

    @pytest.mark.parametrize('blocked_name', sorted(BLOCKED_HEADER_NAMES))
    def test_blocked_names_silently_dropped(self, blocked_name):
        system = {'Accept': 'application/json'}
        custom = {blocked_name: 'sneaky'}
        result = merge_callback_headers(system, custom)
        assert blocked_name not in result

    @pytest.mark.parametrize('prefix', BLOCKED_HEADER_PREFIXES)
    def test_blocked_prefixes_silently_dropped(self, prefix):
        system = {'Accept': 'application/json'}
        custom = {f'{prefix}sneaky': 'value'}
        result = merge_callback_headers(system, custom)
        assert f'{prefix}sneaky' not in result

    def test_mixed_valid_and_blocked_headers(self):
        system = {'Content-Type': 'application/json'}
        custom = {
            'X-Custom': 'kept',
            'authorization': 'dropped',
            'x-forwarded-for': 'dropped',
            'X-Valid': 'also-kept',
        }
        result = merge_callback_headers(system, custom)
        assert result == {
            'Content-Type': 'application/json',
            'X-Custom': 'kept',
            'X-Valid': 'also-kept',
        }
