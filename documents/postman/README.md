# Postman

To download Postman, go [here](https://www.postman.com/downloads/). Postman allows you to send requests.

## Postman collection

The intention of this collection is to provide quick, easy functionality to send email, sms, and application notifications from non-admin users. As a non-admin user one can send a notification and get information regarding the notification. Creation, viewing and editing of templates should be done in the portal and not through the API.  

The postman scripts use the environment variables and populate or update them as the scripts are executed.

The basic development environment variables are in this folder which you can import along with the scripts. 

## basic environment variables

These environment variables should be defined before you can execute any of the scripts
- notification-api-url: `{environment}-api.va.gov/vanotify`
- service-api-key : retrieve this from portal. 
- service-id : retrieve this from the portal
- service-name : retrieve this from the portal. 

## basic notification calls

See Postman collection for details of call to send email, sms, or mobile push. The following are the actions allowed to non-admin users. 

- You can send an email with an email address or a recipient-identifier, so VA Notify can look up the email address.
- You can send a text with a phone number or a recipient-identifier, so VA Notify can look up the email address. 
- You can send a push notification to a Mobile App user. 
- You can get information regarding the status of a notification.

### Example
`````

curl -x POST https:://api-staging.va.gov/vanotify/v2/notifications/email \
 -h 
 -d '{
    "template_id": "{{email-template-id}}",
    "email_address": "john.smith@fake-domain.com"
}
`````

#### Response
`````
{
  "billing_code": null,
  "content": {
    "body": "Test",
    "subject": "Test"
  },
  "id": "<notification-id>",
  "reference": null,
  "scheduled_for": null,
  "template": {
    "id": "<template-id>",
    "uri": "https://dev-api.va.gov/services/<service-id>/templates/<template-id>",
    "version": 1
  },
  "uri": "https://dev-api.va.gov/v2/notifications/<notification-id>"
}
`````