from app.models import EMAIL_TYPE, SMS_TYPE


class TestTemplateBase:
    def test_html_property_returns_none_when_feature_flag_disabled(self, mocker, sample_template):
        """
        Test that TemplateBase.html property returns None when
        STORE_TEMPLATE_CONTENT feature flag is disabled
        """
        mocker.patch('app.models.is_feature_enabled', return_value=False)
        template = sample_template(template_type=EMAIL_TYPE)

        assert template.html is None

    def test_html_property_returns_content_as_html_when_feature_flag_enabled_and_content_as_html_exists(
        self, mocker, sample_template
    ):
        """
        Test that TemplateBase.html property returns content_as_html
        when STORE_TEMPLATE_CONTENT feature flag is enabled and content_as_html exists
        """
        mocker.patch('app.models.is_feature_enabled', return_value=True)
        template = sample_template(template_type=EMAIL_TYPE)
        template.content_as_html = '<p>Some HTML content</p>'

        assert template.html == '<p>Some HTML content</p>'

    def test_html_property_generates_html_for_email_when_feature_flag_enabled_and_content_as_html_not_exists(
        self, mocker, sample_template
    ):
        """
        Test that TemplateBase.html property generates HTML for email templates
        when STORE_TEMPLATE_CONTENT feature flag is enabled but content_as_html is None
        """
        mocker.patch('app.models.is_feature_enabled', return_value=True)
        html_template_mock = mocker.patch('app.models.HTMLEmailTemplate')
        html_template_mock.return_value.__str__.return_value = '<p>Generated HTML content</p>'

        template = sample_template(template_type=EMAIL_TYPE)
        template.content_as_html = None

        assert template.html == '<p>Generated HTML content</p>'
        html_template_mock.assert_called_once_with({'content': template.content, 'subject': template.subject})

    def test_html_property_returns_none_for_sms_when_feature_flag_enabled(self, mocker, sample_template):
        """
        Test that TemplateBase.html property returns None for SMS templates
        even when STORE_TEMPLATE_CONTENT feature flag is enabled
        """
        mocker.patch('app.models.is_feature_enabled', return_value=True)
        template = sample_template(template_type=SMS_TYPE)

        assert template.html is None
