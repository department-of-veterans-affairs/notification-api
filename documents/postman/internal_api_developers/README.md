# Postman

To download Postman, go [here](https://www.postman.com/downloads/). Postman allows you to send requests to test API endpoints.

## About 

This directory contains the Notification-API Postman collection and environment variable files for Development, Performance, and Staging environments.

All JSON files can be imported into Postman individually.

**Note:** While migrating from Notification-API to our Enterprise Notification Platform (ENP), these environment variable files contain variables for both applications.

## Importing Files

1. Open Postman
2. Click **Import** 
3. Select the collection file: `notification-api.json`
4. Import environment files one at a time:
   - `development-environment.json`
   - `performance-environment.json`
   - `staging-environment.json`

## Environment Variables

The Postman collection uses environment variables that are automatically populated or updated as requests are executed.

### Admin Route Variables

Required before executing admin routes:

- **`notification-client-secret`** - Secret key used to generate JWT tokens. Found in AWS Parameter Store for the appropriate environment.
- **`notification-admin-id`** - Admin user ID. Found in AWS Parameter Store for the appropriate environment.


### Service Route Variables

Required before executing service routes:

- **`service-id`** - Individual service ID for a particular service. Found by logging into VANotify Portal as an Admin user.
- **`service-api-key`** - Service API key. Created by Admin users through the "create api key for service" endpoint in the Notification-API collection.