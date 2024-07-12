from flask import current_app, url_for


def build_dynamic_ga4_pixel_tracking_url(notification):
    """
    Constructs a dynamic URL that contains information on the notification email being sent.
    The dynamic URL is used to for pixel tracking and sends a request to our application when
    email is openned.  

    :param notification: The notification object containing template and service details.
    :return: A dynamically constructed URL string.
    """

    ga4_url = url_for('ga4.get_ga4', _external=True)
    url = (
        f'{ga4_url}?'
        f'campaign={notification.template.name}&campaign_id={notification.template.id}&'
        f'name=email_opens&source=vanotify&medium=email&'
        f'content={notification.service.name}/{notification.service.id}/{notification.id}'
    )

    current_app.logger.info(f'Generated google analytics 4 pixel URL: {url}')
    return url
