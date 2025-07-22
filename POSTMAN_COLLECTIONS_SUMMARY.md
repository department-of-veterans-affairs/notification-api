# Postman Collections Summary (Post-Restoration)

## Overview
After restoring the Postman collections from git history and performing a careful analysis, the collections now contain endpoints that align well with the available Flask endpoints (69 Flask endpoints vs 50 Postman endpoints).

## Collections

### Internal API Developers Collection
**File:** `documents/postman/internal_api_developers/notification-api.postman_collection.json`  
**Endpoints:** 47

#### Available Endpoints by Category

**Status/Health (1 endpoint)**
- `GET /_status` (healthcheck)

**User Management (2 endpoints)**
- `GET /user` (list users)
- `GET /user/{user_id}` (get specific user)

**V2 Notifications (3 endpoints)**
- `POST /v2/notifications/push` (send push notification)
- `POST /v2/notifications/push/broadcast` (broadcast push notification)
- `GET /v2/notifications/{notification_id}` (get notification status)

**V3 Notifications (2 endpoints)**
- `POST /v3/notifications/email` (send email)
- `POST /v3/notifications/sms` (send SMS)

**Service Management (3 endpoints)**
- `GET /service` (list services)
- `GET /service/{service_id}` (get specific service)
- `POST /service/{service_id}` (update service)

**API Keys (3 endpoints)**
- `POST /service/{service_id}/api-key` (create API key)
- `GET /service/{service_id}/api-keys` (list API keys)
- `POST /service/{service_id}/api-key/revoke/{api_key_id}` (revoke API key)

**Templates (10 endpoints)**
- `GET /service/{service_id}/template` (list templates)
- `POST /service/{service_id}/template` (create EMAIL template)
- `POST /service/{service_id}/template` (create SMS template)
- `GET /service/{service_id}/template/{template_id}` (get template)
- `POST /service/{service_id}/template/{email_template_id}` (update EMAIL template)
- `POST /service/{service_id}/template/{sms_template_id}` (update SMS template)
- `GET /service/{service_id}/template/{template_id}/preview-html` (get HTML preview)
- `GET /service/{service_id}/template/{template_id}/stats` (get template stats)

**Service Callbacks (6 endpoints)**
- `POST /service/{service_id}/callback` (create callback)
- `GET /service/{service_id}/callback` (list callbacks)
- `GET /service/{service_id}/callback/{callback_id}` (get callback)
- `POST /service/{service_id}/callback/{callback_id}` (update callback)
- `DELETE /service/{service_id}/callback/{callback_id}` (delete callback)

**SMS Senders (3 endpoints)**
- `POST /service/{service_id}/sms-sender` (create SMS sender)
- `GET /service/{service_id}/sms-sender` (list SMS senders)
- `POST /service/{service_id}/sms-sender/{sms_sender_id}` (update SMS sender)

**Communication Items (5 endpoints)**
- `GET /communication-item` (list all communication items)
- `POST /communication-item` (create communication item)
- `GET /communication-item/{communication_item_id}` (get communication item)
- `PATCH /communication-item/{communication_item_id}` (partially update communication item)
- `DELETE /communication-item/{communication_item_id}` (delete communication item)

**Inbound Numbers (6 endpoints)**
- `POST /inbound-number` (create inbound number)
- `GET /inbound-number` (list inbound numbers)
- `GET /inbound-number/available` (get available inbound numbers)
- `GET /inbound-number/service/{service_id}` (get inbound numbers for service)
- `POST /inbound-number/{inbound_number_id}` (update inbound number)
- `POST /inbound-number/{inbound_number_id}/off` (deactivate inbound number)

**Provider Details (3 endpoints)**
- `GET /provider-details` (list provider details)
- `GET /provider-details/{provider_detail_id}` (get provider detail)
- `POST /provider-details/{provider_detail_id}` (update provider detail)

### Simplified Collection
**File:** `documents/postman/notification-api-simplified.postman_collection.json`  
**Endpoints:** 3

#### Available Endpoints
- `POST /v2/notifications/push` (send push notification)
- `POST /v2/notifications/push/broadcast` (broadcast push notification)  
- `GET /v2/notifications/{notification_id}` (get notification status)

## Missing Flask Endpoints
The following Flask endpoints are available but not currently in Postman collections:

**Service Billing (4 endpoints)**
- `GET /service/{service_id}/billing/yearly-usage-summary`
- `GET /service/{service_id}/billing/ft-yearly-usage-summary`
- `GET /service/{service_id}/billing/monthly-usage`
- `GET /service/{service_id}/billing/ft-monthly-usage`

**Service Statistics & History (3 endpoints)**
- `GET /service/{service_id}/history`
- `GET /service/{service_id}/statistics`
- `GET /service/{service_id}/template-statistics`

**Inbound SMS (2 endpoints)**
- `GET /service/{service_id}/inbound-sms/{inbound_sms_id}`
- `POST /service/{service_id}/inbound-sms`

**Additional Template Features (3 endpoints)**
- `POST /service/{service_id}/template/generate-preview`
- `GET /service/{service_id}/template/{template_id}/version/{version}`
- `GET /service/{service_id}/template/{template_id}/versions`

**V2 Templates (4 endpoints)**
- `GET /v2/templates`
- `GET /v2/template/{template_id}`
- `GET /v2/template/{template_id}/version/{version}`
- `POST /v2/template/{template_id}/preview`

**Platform Stats (2 endpoints)**
- `GET /platform-stats`
- `GET /platform-stats/monthly`

**GA4 Analytics (1 endpoint)**
- `GET /ga4/open-email-tracking/{notification_id}`

**Extended Status (1 endpoint)**
- `GET /_status/live-service-and-organisation-counts`

**V2 Notifications (2 endpoints)**
- `GET /v2/notifications` (list notifications)
- `POST /v2/notifications/{notification_type}` (send notification by type)

## Summary

- **Flask endpoints available:** 69
- **Postman endpoints (both collections):** 50
- **Coverage:** ~72% of Flask endpoints are testable via Postman
- **Missing endpoints:** 19 (primarily billing, stats, v2 templates, and platform analytics)

## Recommendations

1. **High Priority**: Add billing and service statistics endpoints for financial reporting
2. **Medium Priority**: Add inbound SMS management endpoints
3. **Low Priority**: Add platform stats and GA4 analytics endpoints
4. **Consider**: Whether v2 template endpoints are still needed or if v3 should be prioritized

The current collections cover all core notification functionality and essential service management operations. Missing endpoints are primarily related to reporting, analytics, and legacy v2 template operations.