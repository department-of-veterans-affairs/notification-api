# ADR-001: Custom Callback Headers

## Status

Proposed

## Date

2026-02-11

## Context

VA Notify sends delivery status callbacks to consumer services via two mechanisms:

1. **Service-level callbacks** — configured once per service with a webhook URL and bearer token. Headers sent: `Content-Type: application/json` and `Authorization: Bearer <token>`.
2. **Notification-level callbacks** — a `callback_url` provided per notification request. Headers sent: `Content-Type: application/json` and `x-enp-signature: <hmac>`.

Consumer teams have requested the ability to include additional HTTP headers in these callbacks. The immediate use case is a team whose callback endpoint sits behind an AWS API Gateway that requires an `x-api-key` header. Without custom header support, these teams must build workarounds such as a proxy layer or an alternative ingress path.

## Decision

Add support for an optional `callback_headers` field (a dictionary of string key-value pairs) on both service-level and notification-level callbacks.

### Approach: Validated key-value dictionary (encrypted at rest)

We will store custom headers as a validated key-value dictionary rather than supporting fully arbitrary headers or a single explicit header like `x-api-key`. The logical format is a JSON object; the physical column is `db.String` containing an encrypted blob (see Security §1).

### Why not fully arbitrary headers?

- Arbitrary headers increase the SSRF attack surface — a caller could direct VA Notify to authenticate against internal services with spoofed headers.
- A blocklist of dangerous headers is fragile and hard to maintain as infrastructure evolves.

### Why not a single `x-api-key` field?

- Minimal additional effort to support a dictionary vs. a single field.
- Avoids a new migration every time a consumer needs a different header name.
- The general approach cleanly handles future use cases (`x-correlation-id`, `x-request-id`, etc.).

## Specification

### API surface

**Notification-level** — new optional field on `POST /v2/notifications/email` and `POST /v2/notifications/sms`:

```json
{
  "template_id": "...",
  "email_address": "...",
  "callback_url": "https://consumer.va.gov/callbacks",
  "callback_headers": {
    "x-api-key": "gateway-key-value"
  }
}
```

`callback_headers` is only valid when `callback_url` is also provided. It has no effect otherwise.

**Service-level** — new optional field on `POST /service/{service_id}/callback`:

```json
{
  "url": "https://consumer.va.gov/callbacks",
  "bearer_token": "...",
  "callback_type": "delivery_status",
  "callback_channel": "webhook",
  "callback_headers": {
    "x-api-key": "gateway-key-value"
  }
}
```

### Validation constraints

| Constraint               | Limit                                              |
|--------------------------|----------------------------------------------------|
| Max number of headers    | 5                                                  |
| Min header name length   | 1 character                                        |
| Max header name length   | 256 characters                                     |
| Header name character set| RFC 7230 token characters only (`A-Z a-z 0-9 !#$%&'*+-.^_\`\|~`) |
| Min header value length  | 1 character                                        |
| Max header value length  | 1024 characters                                    |
| Header value type        | String only                                        |
| Empty dict `{}`          | Accepted; treated as absent (no custom headers)    |

Blocked header names (case-insensitive):

- `authorization`, `content-type`, `content-length`, `transfer-encoding`, `connection`, `host`, `cookie`

Blocked header name prefixes (case-insensitive):

- `x-forwarded-`, `x-real-`, `x-amz-`, `x-envoy-`

For notification-level callbacks, `x-enp-signature` is also blocked (reserved by VA Notify).

### Header merge behavior

Custom headers are added to the outbound request **after** system headers. They cannot override system headers — any blocked header that passes validation is still filtered at send time as a defense-in-depth measure.

Custom headers apply to **webhook-channel callbacks only**. Queue-channel callbacks (SQS) do not use HTTP headers. If a service callback is configured with `callback_channel: "queue"`, `callback_headers` is accepted and stored but has no effect — headers are not included in SQS message attributes.

**Service-level outbound headers:**

```
Content-Type: application/json
Authorization: Bearer <token>
<custom headers>
```

**Notification-level outbound headers:**

```
Content-Type: application/json
x-enp-signature: <hmac>
<custom headers>
```

### Precedence

If a notification includes `callback_url` (with or without `callback_headers`), it overrides the service-level callback entirely. Service-level `callback_headers` are not merged with notification-level headers.

## Security Considerations

### 1. Secrets at rest — Encrypt the blob

Header values will frequently contain secrets (API keys, tokens). The `callback_headers` value must be **encrypted at rest** using the same `app.encryption.encrypt()`/`decrypt()` pattern used for `bearer_token` on `ServiceCallback`. The database column type is `db.String` (encrypted blob), not plaintext JSONB.

### 2. Secrets in transit via Celery — Pass encrypted via message

For notification-level callbacks, the `send_delivery_status_from_notification` Celery task receives callback parameters (`callback_url`, `callback_signature`, `notification_data`) as plaintext kwargs in the SQS message. `callback_headers` will also be passed via the Celery SQS message, but **encrypted** using `app.encryption.encrypt()` before enqueuing and decrypted inside the worker before use. The kwarg should be named `encrypted_callback_headers` to signal that decryption is required, consistent with the `encrypted_status_update` convention on the service-level path.

This creates a mixed pattern: the notification-level SQS message will contain three plaintext kwargs alongside one encrypted kwarg. The notification-level path currently passes **all** data unencrypted — including recipient PII (`to`) and client references in `notification_data`. The service-level path, by contrast, bundles all data into a single encrypted blob via `create_delivery_status_callback_data()`. We are encrypting only `callback_headers` here because it contains secrets (API keys, tokens); broader encryption cleanup of the notification-level path is deferred to follow-on work (see below).

A "load from DB" approach was considered but rejected because of a race condition: `send_delivery_status_from_notification` retries up to 60 times with exponential backoff (max 5 minutes between attempts). The default notification retention is 7 days but can be configured per-service. If a notification is archived to `notification_history` while retries are still in-flight, a DB lookup on the `notifications` table would fail — `notification_history` deliberately excludes `callback_headers`. Passing the encrypted value through the message avoids this race entirely.

SQS messages are encrypted at rest (SSE-SQS) and in transit (HTTPS). The application-level encryption adds a second layer, ensuring that even if SQS message contents are exposed (e.g., via CloudWatch logs or dead-letter queue inspection), header values remain opaque.

### 3. SSRF amplification

The caller already controls `callback_url`, which is the primary SSRF vector. Adding `callback_headers` incrementally increases risk because a malicious caller could include authentication headers that internal services trust. Mitigations:

- The header blocklist prevents common infrastructure/proxy headers.
- Existing `callback_url` validation (must be HTTPS) and network-level controls (Celery workers should not reach internal service meshes) remain the primary defense.
- The blocklist is a best-effort defense-in-depth measure, not a complete solution.

### 4. Log leakage

Callback header values must never be logged. The existing codebase logs `callback.url` on failure — this is acceptable. Logging header values is not. Code review should enforce this.

### 5. HTTP request smuggling

The Python `requests` library sanitizes header values, preventing injection of newlines or other control characters. The blocklist for `Transfer-Encoding`, `Content-Length`, `Host`, and `Connection` adds defense-in-depth.

## Implementation Scope

### notification-api (primary)

| Area | Files | Change |
|------|-------|--------|
| DB migration | `migrations/versions/` | Add `callback_headers` column to `service_callback` and `notifications` tables. `service_callback_history` receives the column automatically via the `Versioned` mixin. Do NOT add to `notification_history` (see rationale below). |
| Models | `app/models.py` | Add `callback_headers` to `ServiceCallback`, `DeliveryStatusCallbackApiData`, and `Notification`. Do NOT add to `NotificationHistory`. |
| Validation | `app/schema_validation/callback_headers.py` (new) | Header name/value validation with blocklist |
| Service callback schema | `app/service/service_callback_api_schema.py` | Add `callback_headers` to create/update JSON schemas |
| Marshmallow schema | `app/schemas.py` | Add `callback_headers` to `ServiceCallbackSchema` fields |
| DAO | `app/dao/service_callback_api_dao.py` | Include `callback_headers` in `DeliveryStatusCallbackApiData` construction (3 functions) |
| Notification schema | `app/v2/notifications/notification_schemas.py` | Add `callback_headers` to `post_sms_request` and `post_email_request` |
| Persist notification | `app/notifications/process_notifications.py` | Add `callback_headers` parameter |
| V2 POST handlers | `app/v2/notifications/post_notifications.py` | Pass `callback_headers` from form to `persist_notification` |
| Webhook strategy | `app/callback/webhook_callback_strategy.py` | Merge custom headers into outbound request (service-level path) |
| Notification callback task | `app/celery/service_callback_tasks.py` | In `check_and_queue_notification_callback_task`, encrypt and pass as `encrypted_callback_headers` kwarg; in `send_delivery_status_from_notification`, accept `encrypted_callback_headers`, decrypt, and merge into outbound request (notification-level path) |

**Important — two separate code paths require header injection:**

1. **Service-level:** `WebhookCallbackStrategy.send_callback()` in `webhook_callback_strategy.py` — reads headers from `DeliveryStatusCallbackApiData`.
2. **Notification-level:** `send_delivery_status_from_notification()` in `service_callback_tasks.py` — calls `requests.post()` directly (does NOT use the webhook strategy). Encrypted `callback_headers` are passed via the Celery SQS message, decrypted in the worker, and merged inline.

A shared utility function (e.g., `merge_callback_headers(system_headers, custom_headers, blocked_names)`) should be extracted to avoid duplicating the merge-and-filter logic across both paths.

### notification-portal (secondary)

| Area | Files | Change |
|------|-------|--------|
| OpenAPI spec | `public/swagger/openapi.yaml` | Add `callback_headers` to request/response schemas and examples |
| Documentation | `app/views/developer/tech_info.html.erb` | Document custom callback headers in status callbacks section |
| Admin UI | Callback management views (if applicable) | Add `callback_headers` input to service callback create/edit forms |

### vanotify-infra

No infrastructure changes required. SQS queues, ALB listener rules, and lambda functions are unaffected.

## Excluded from Scope

### `notification_history` table

`callback_headers` is NOT added to `notification_history`. The existing `callback_url` column is also absent from `notification_history` — this is intentional. History tables omit ephemeral and secret-bearing fields (`_personalisation`, `to`, `normalised_to`, `callback_url`). Callback headers are only needed while a notification is live and callbacks are in-flight; they have no audit value after delivery completes. The `insert_update_notification_history` bulk SQL (`INSERT ... FROM SELECT` driven by `NotificationHistory.__table__.c`) safely ignores columns that exist on `notifications` but not on `notification_history` — no coupling concern.

Because notification-level `callback_headers` are passed encrypted through the Celery message (see Security §2), callbacks continue to work correctly even after the notification is archived and the `notifications` row is deleted.

### Complaint callbacks

Complaint callbacks are **automatically covered** by this change with no additional work. Although the DAO function `get_service_complaint_callback_api_for_service()` returns a raw `ServiceCallback` ORM object (not the `DeliveryStatusCallbackApiData` dataclass), the Celery task `send_complaint_to_service` re-fetches the callback via `get_service_callback(service_callback_id)`, which wraps it into a `DeliveryStatusCallbackApiData` dataclass. From there, it flows through `service_callback_send()` → `WebhookCallbackStrategy.send_callback()` — the same path as delivery status callbacks. Because `callback_headers` is being added to both `ServiceCallback` (the model) and `DeliveryStatusCallbackApiData` (the dataclass), and the header merge happens in `WebhookCallbackStrategy`, complaint callbacks will pick up custom headers automatically.

No changes to the complaint-specific DAO function or Celery task are required.

## Caching Impact

The `DeliveryStatusCallbackApiData` dataclass is cached with a 600-second TTL in `service_callback_api_dao.py`. Changes to a service's `callback_headers` will take up to 10 minutes to take effect. This is consistent with existing behavior for `url` and `bearer_token` changes. This cache delay should be documented in the API reference so consumers are aware that service-level header changes are not immediate.

## Alternatives Considered

| Alternative | Pros | Cons |
|---|---|---|
| Single `callback_api_key` field | Simplest implementation; one column, one header | Cannot support other header names; new migration per header type |
| Fully arbitrary headers (no blocklist) | Maximum flexibility | Unacceptable security risk; enables auth spoofing against internal services |
| Consumer-side proxy | No VA Notify changes needed | Pushes complexity to every consumer; defeats the purpose of a managed callback |

## Follow-on Work

### Encrypt notification-level Celery message payload

The notification-level callback path (`check_and_queue_notification_callback_task` → `send_delivery_status_from_notification`) currently passes all kwargs — including recipient PII (`to`) and client references — as plaintext through SQS. The service-level path encrypts equivalent data into a single blob. This ADR adds `encrypted_callback_headers` as a selectively encrypted kwarg, creating a mixed plaintext/encrypted pattern in the same message.

A follow-on effort should align the notification-level path with the service-level pattern by encrypting the full payload into a single blob (similar to `create_delivery_status_callback_data()`). This would:

- Eliminate the mixed encryption pattern introduced by this ADR
- Protect recipient PII that currently travels in the clear through SQS
- Simplify the worker signature to match the service-level convention

This is pre-existing tech debt unrelated to custom callback headers, but this ADR makes it more visible.

## Consequences

- Consumer teams behind API gateways can receive callbacks without building proxy infrastructure.
- A small increase in SSRF attack surface, mitigated by header blocklist and existing network controls.
- Custom header values are secrets and must be treated with the same care as bearer tokens (encrypted at rest and in Celery messages, excluded from logs).
- The notification-level Celery message will contain a mix of plaintext and encrypted kwargs until the follow-on encryption work is completed.
- The 600s cache TTL for service-level callbacks applies to header changes as well.
