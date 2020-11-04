from flask import current_app


def build_ga_pixel_url(notification, provider):
    url_params = {
        'v': '1',
        't': 'event',
        'tid': 'UA-50123418-16',
        'cid': notification.id,
        'aip': '1',
        'ec': 'email',
        'ea': 'open',
        'el': notification.template.name,
        'dp': '/email/vanotify/{}/{}/{}'.format(
            notification.service.organisation.name,
            notification.service.name,
            notification.template.name
        ),
        'dt': notification.subject,
        'cn': notification.template.name,
        'cs': provider.get_name(),
        'cm': 'email',
        'ci': notification.template.id
    }

    url = '&'.join('{}={}'.format(key, value) for key, value in url_params.items())

    current_app.logger.info(
        "generated google analytics pixel URL is {}".format(url)
    )
    return url
