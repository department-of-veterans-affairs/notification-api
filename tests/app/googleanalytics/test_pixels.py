from app.googleanalytics.pixels import build_dynamic_ga4_pixel_tracking_url


class TestGA4PixelTrackingURL:
    def test_build_dynamic_ga4_pixel_tracking_url_contains_expected_parameters(
        self,
        notify_api,
        sample_notification_model_with_organization,
    ):
        with notify_api.test_request_context():
            url = build_dynamic_ga4_pixel_tracking_url(sample_notification_model_with_organization)

            all_expected_parameters = [
                'campaign=',
                'campaign_id=',
                'name=email_opens',
                'source=vanotify',
                'medium=email',
                'content=',
            ]

            assert all(parameter in url for parameter in all_expected_parameters)
