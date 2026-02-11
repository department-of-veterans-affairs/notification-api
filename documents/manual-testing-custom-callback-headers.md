# Manual Testing: Custom Callback Headers (ADR-001)

> **Note:** This implementation is a **proposal / proof-of-concept**. It demonstrates the feasibility and design of custom callback headers for team review and discussion.

## Summary

End-to-end manual testing confirmed that this proof-of-concept implementation works as designed: custom callback headers configured on a `ServiceCallback` are included in outgoing webhook POST requests to the consumer's endpoint. A notification was sent via the v2 API, Celery processed it and triggered the delivery status callback, and **webhook.site** received the request with the expected custom headers (`X-Api-Key` and `X-Correlation-Id`).

The test exercised the full production code path:
1. API receives notification → persists to DB → queues to Celery
2. Celery `deliver_email` task processes notification → status becomes `permanent-failure` (expected — no email provider in local stack)
3. Celery `send-delivery-status` task fires → looks up `ServiceCallback` with matching `notification_statuses` → finds callback with `callback_headers`
4. `WebhookCallbackStrategy.send` merges custom headers into the outgoing POST request
5. webhook.site receives the callback with both custom headers present

## Prerequisites

- Docker and Docker Compose installed
- notification-api repo checked out on `feature/custom-callback-headers` branch
- Migration `0384_add_callback_headers` included in the build

## Reproduction Steps

### 1. Build and start the local stack

```bash
cd notification-api

# Build the image
docker build -t notification_api -f ci/Dockerfile .

# Temporarily set NOTIFY_ENVIRONMENT to development (the test config
# uses a dummy Celery broker that can't actually queue tasks)
cd ci
sed -i '' 's/NOTIFY_ENVIRONMENT=test/NOTIFY_ENVIRONMENT=development/' .local.env

# Start all services
docker compose -f docker-compose-local.yml up --no-build -d

# Wait for the app to become healthy
sleep 15
curl -s http://localhost:6011/_status | python3 -m json.tool
# Verify "status": "ok" and "db_version": "0384_add_callback_headers"
```

### 2. Set up a callback receiver

Go to [https://webhook.site](https://webhook.site) and copy your unique URL. This will be used as the callback endpoint.

### 3. Configure the service callback with custom headers

Create a Python script (or use `flask shell` inside the container) to set up the required database entities:

```bash
docker exec -w /app ci_app_1 /.venv/bin/python -c "
import sys, secrets
sys.path.insert(0, '/app')
from flask import Flask
from app import create_app
from app.models import ApiKey, ServiceCallback, Service, Template, DELIVERY_STATUS_CALLBACK_TYPE
from app.db import db
from datetime import datetime, timedelta

application = Flask('app', static_folder=None)
create_app(application)
with application.app_context():
    svc = db.session.query(Service).first()
    user = svc.users[0]
    user.platform_admin = True

    # Create API key with expiry_date set
    key = ApiKey(
        service_id=svc.id,
        name='manual-test-key',
        created_by_id=user.id,
        key_type='normal',
        expiry_date=datetime.utcnow() + timedelta(days=30),
        secret=secrets.token_urlsafe(64),
    )
    db.session.add(key)

    # Create service callback with custom headers
    cb = ServiceCallback(
        service_id=svc.id,
        url='<YOUR_WEBHOOK_SITE_URL>',
        callback_type=DELIVERY_STATUS_CALLBACK_TYPE,
        callback_channel='webhook',
        bearer_token='manual-test-bearer-token',
        updated_by_id=user.id,
        callback_headers={
            'X-Api-Key': 'my-secret-key-123',
            'X-Correlation-Id': 'manual-test-001',
        },
    )
    db.session.add(cb)
    db.session.commit()

    tmpl = db.session.query(Template).filter_by(service_id=svc.id, template_type='email').first()

    print(f'SERVICE_ID={svc.id}')
    print(f'API_KEY_SECRET={key.secret}')
    print(f'TEMPLATE_ID={tmpl.id}')
"
```

Note the `SERVICE_ID`, `API_KEY_SECRET`, and `TEMPLATE_ID` from the output.

### 4. Restart the Celery worker

The callback lookup function uses a 10-minute TTL cache. If any notifications were sent before the callback was created, the cache will hold a stale "no callback" result. Restart Celery to clear it:

```bash
docker restart ci_celery_1
sleep 15  # wait for celery to become healthy
```

### 5. Send a notification

Generate a JWT token and send the notification in a single command (the JWT has a ~30-second TTL):

```bash
TOKEN=$(docker exec -w /app ci_app_1 /.venv/bin/python -c "
from notifications_python_client.authentication import create_jwt_token
print(create_jwt_token('<API_KEY_SECRET>', '<SERVICE_ID>'))
") && \
curl -s -X POST "http://localhost:6011/v2/notifications/email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email_address": "test@example.com",
    "template_id": "<TEMPLATE_ID>",
    "personalisation": {
      "message": "Testing custom callback headers",
      "subject": "Custom Headers Test"
    }
  }' | python3 -m json.tool
```

A successful response returns the notification ID:
```json
{
    "id": "83d4d068-cf2a-4b1e-8671-9f2b8c1c3ab8",
    "template": { ... },
    ...
}
```

### 6. Verify the callback

**Check Celery logs** to confirm the callback was sent:

```bash
docker logs ci_celery_1 2>&1 | grep -i "callback sent"
```

Expected log output:
```
Callback sent to https://webhook.site/..., response 200, notification_id: 83d4d068-...
```

**Check webhook.site** to verify the custom headers are present on the incoming request.

### 7. Clean up

Revert the environment change:

```bash
cd ci
sed -i '' 's/NOTIFY_ENVIRONMENT=development/NOTIFY_ENVIRONMENT=test/' .local.env
docker compose -f docker-compose-local.yml down
```

## Results

The callback was received at webhook.site with both custom headers present:

| Header | Value |
|---|---|
| `x-api-key` | `my-secret-key-123` |
| `x-correlation-id` | `manual-test-001` |

### Screenshot

<img width="1604" height="782" alt="Screenshot 2026-02-11 at 15 33 18" src="https://github.com/user-attachments/assets/d28049f4-0637-4437-82ab-b4f45dcbf8a7" />


## Notes

- The local stack does not have an email provider configured, so notifications go to `permanent-failure` status immediately. This is expected and still triggers the delivery status callback.
- The `get_service_delivery_status_callback_api_for_service` DAO function uses a `TTLCache(maxsize=1024, ttl=600)` (10-minute cache). If you create or modify a callback, you must restart the Celery worker or wait for the cache to expire before the change takes effect.
- The v2 API JWT tokens generated by `create_jwt_token` have a ~30-second TTL. Generate and use them in a single command to avoid expiry.
