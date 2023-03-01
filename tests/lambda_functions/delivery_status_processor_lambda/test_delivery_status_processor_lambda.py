# TEST: missing environment variables cause the system to exit 
# TEST: valid_event() returns True when the event is valid
# TEST: valid_event() returns False when the event is invalid
# TEST: event_to_celery_body_mapping() returns a dict with body and provider if headers.user-agent contains TwilioProxy
# TEST: event_to_celery_body_mapping() returns None if headers.user-agent does not contain TwilioProxy
# TEST: event_to_celery_body_mapping() returns None, the event is enqueued on dead letter queue
# TEST: celery_body_to_celery_task() returns a dict with an envelope that has a body = base 64 encoded task and that base 64 encoded task  contains Message key with the task_message


