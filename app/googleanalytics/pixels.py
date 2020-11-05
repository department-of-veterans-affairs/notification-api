import urllib.parse as url_parser

from flask import current_app


def build_ga_pixel_url(notification, provider, urlencode=None):
    url_params = {
        'v': '1',
        't': 'event',
        'tid': current_app.config['GOOGLE_ANALYTICS_TID'],
        'cid': notification.id,
        'aip': '1',
        'ec': 'email',
        'ea': 'open',
        'el': url_parser.quote(notification.template.name),
        'dp': url_parser.quote(
            f"/email/vanotify/{notification.service.organisation.name}"
            f"/{notification.service.name}"
            f"/{notification.template.name}",
            safe=''),
        'dt': url_parser.quote(notification.subject),
        'cn': url_parser.quote(notification.template.name),
        'cs': provider.get_name(),
        'cm': 'email',
        'ci': notification.template.id
    }

    url = current_app.config['GOOGLE_ANALYTICS_URL']
    url += '&'.join(f"{key}={value}" for key, value in url_params.items())

    current_app.logger.info(
        f"generated google analytics pixel URL is {url}"
    )
    return url
