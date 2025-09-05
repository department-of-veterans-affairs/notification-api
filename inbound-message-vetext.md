**Current State**
* How does an inbound message from **Twilio** currently flow through our system to reach VEText?
  - Veteran texts Twilio number → Twilio webhook POST to `api.va.gov/twoway/vettext` → ALB routes to `vetext_incoming_forwarder_lambda.py` → Database lookup in `inbound_numbers` table → Forward to VEText Twilio endpoint

* How does an inbound message from **AWS** currently flow through our system to reach VEText?
  - Veteran texts AWS number → AWS Pinpoint → SQS Queue → `two_way_sms_v2.py` Lambda → Database lookup in `inbound_numbers` table → Forward to VEText AWS endpoint

* What components (Lambdas, API endpoints, database tables, etc.) are involved in each path?
  - **Twilio**: Twilio webhook to `api.va.gov/twoway/vettext` → ALB → `vetext_incoming_forwarder_lambda` → `inbound_numbers` table → VEText endpoint `/inbound/vetext/pub/inbound-message/twilio` + Twilio retry queue (3s delay) + Twilio dead letter queue
  - **AWS**: SQS → `two_way_sms_v2` Lambda → `inbound_numbers` table → VEText endpoint `/api/vetext/pub/inbound-message/aws` + AWS retry queue (120s delay) + AWS dead letter queue

* (*Optional*) What are the differences in payload structure or metadata between Twilio and AWS messages?
  - **Twilio**: URL-encoded form data with fields like `From`, `To`, `Body`, `MessageSid`, `AccountSid`
  - **AWS**: JSON format with fields like `originationNumber`, `destinationNumber`, `messageBody`
  
**Routing & Configuration**
* Where is the inbound number routing configured (e.g. inbound numbers table, environment variables, ALB, etc.)?
    #TODO - Need to confirm
  - `inbound_numbers` database table contains mappings of phone numbers to `service_id`, `url_endpoint`, `self_managed`, and `auth_parameter`

* How does the system decide whether to send an inbound message to the AWS endpoint or the Twilio endpoint?
  - Provider-specific infrastructure routes to different VEText endpoints, not logic-based decision making. Twilio webhooks go to Twilio Lambda → Twilio VEText endpoint; AWS messages go to AWS Lambda → AWS VEText endpoint

* Does any logic govern this flow, or is it all configuration based? (Check lambdas)
  - Pure configuration-based. Both Lambdas perform the same database lookup by destination number - no routing logic in the code

**Transition Readiness**
* If we move a number from Twilio to AWS, what changes (if any) are required in:
  * Database configuration (inbound numbers table, etc.)?
    - Update the `inbound_numbers` table entry for the migrated number to point to the AWS VEText endpoint instead of Twilio endpoint
  * Lambda configuration/code?
    - No code changes needed - both Lambdas use the same database lookup pattern
  * API Gateway or other routing infrastructure?
    - Configure AWS Pinpoint SMS sender for the number; remove/update Twilio webhook configuration; no ALB changes needed

**Failure Handling**
* How are errors handled if an inbound message fails to forward to VEText?
  - Both paths use SQS retry queues with dead letter queues for permanent failures

* Do Twilio and AWS have different retry mechanisms or failure responses that we need to account for?
  - Yes: AWS uses 120-second retry delay, Twilio uses 3-second retry delay. Different timing patterns need consideration during transition

**Next Steps**
* What tickets will be needed to enable a smooth transition?
  - Update `inbound_numbers` table entries for migrated numbers
  - Configure AWS Pinpoint senders during migration window
  - Update monitoring/alerting for new message flows
  - Test error handling with AWS retry mechanisms

* What testing/validation should be performed before moving production numbers? (if any)
  - Test database routing with non-production numbers
  - Validate VEText AWS endpoint receives correct payload format
  - Test error scenarios and retry queue behavior
  - Monitor both message paths during migration for split traffic validation