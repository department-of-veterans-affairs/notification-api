from flask import current_app, url_for


def build_dynamic_ga4_pixel_tacking_url(notification):
    """
    Constructs a dynamic URL that contains information on the notification email being sent.

    :param notification: The notification object containing template and service details.
    :return: A dynamically constructed URL string.
    """

    root_url = url_for('index', _external=True)
    url = (
        f'{root_url}/ga4/open-email-tracking?'
        f'campaign={notification.template.name}&campaign_id={notification.template.id}&'
        f'name=email_opens&source=vanotify&medium=email&'
        f'content={notification.service.name}/{notification.service.id}/{notification.id}'
    )

    current_app.logger.info(f'Generated google analytics 4 pixel URL: {url}')
    return url