# Lambdas and the Layers they use

| Lambda Name | Layers Used |
| ---- | ---- |
| bip_kafka_consumer_lambda | kafka-consumer |
| bip_msg_mpi_lookup_lambda | aiohttp |
| delivery_status_processor_lambda | twilio |
| nightly_billing_stats_upload_lambda | bigquery |
| nightly_stats_bigquery_upload_lambda | bigquery |
| pinpoint_callback_lambda |  |
| pinpoint_inbound_sms_lambda |  |
| ses_callback_lambda |  |
| two_way_sms_v2 | psycopg2-binary, requests |
| va_profile_opt_in_out_lambda | psycopg2-binary, pyjwt |
| va_profile_remove_old_opt_outs_lambda | psycopg2-binary |
| vetext_incoming_forwarder_lambda | twilio |

**Note on PyJWT Layer:**  
Whenever PyJWT[crypto] (pyjwt-layer) is updated, we also must update the pyjwt requirement in api `requirements_for_test.txt` file.