from collections import defaultdict
from datetime import datetime

from notifications_utils.timezones import convert_utc_to_local_timezone

from app.constants import NOTIFICATION_STATUS_TYPES, TEMPLATE_TYPES
from app.dao.date_util import get_months_for_financial_year


def format_statistics(statistics):
    # statistics come in a named tuple with uniqueness from 'notification_type', 'status' - however missing
    # statuses/notification types won't be represented and the status types need to be simplified/summed up
    # so we can return emails/sms * created, sent, and failed
    counts = create_zeroed_stats_dicts()
    for row in statistics:
        # any row could be null, if the service either has no notifications in the notifications table,
        # or no historical data in the ft_notification_status table.
        if row.notification_type:
            _update_statuses_from_row(counts[row.notification_type], row)

    return counts


def format_admin_stats(statistics):
    counts = create_stats_dict()

    for row in statistics:
        if row.key_type == 'test':
            counts[row.notification_type]['test-key'] += row.count
        else:
            counts[row.notification_type]['total'] += row.count
            if row.status in ('permanent-failure', 'temporary-failure', 'virus-scan-failed'):
                counts[row.notification_type]['failures'][row.status] += row.count

    return counts


def create_stats_dict():
    stats_dict = {}
    for template in TEMPLATE_TYPES:
        stats_dict[template] = {}

        for status in ('total', 'test-key'):
            stats_dict[template][status] = 0

        stats_dict[template]['failures'] = {
            'permanent-failure': 0,
            'temporary-failure': 0,
            'virus-scan-failed': 0,
        }
    return stats_dict


def format_monthly_template_notification_stats(
    year,
    rows,
):
    stats = {
        datetime.strftime(date, '%Y-%m'): {}
        for date in [datetime(year, month, 1) for month in range(4, 13)]
        + [datetime(year + 1, month, 1) for month in range(1, 4)]
    }

    for row in rows:
        formatted_month = row.month.strftime('%Y-%m')
        if str(row.template_id) not in stats[formatted_month]:
            stats[formatted_month][str(row.template_id)] = {
                'name': row.name,
                'type': row.template_type,
                'counts': dict.fromkeys(NOTIFICATION_STATUS_TYPES, 0),
            }
        stats[formatted_month][str(row.template_id)]['counts'][row.status] += row.count

    return stats


def create_zeroed_stats_dicts():
    return {
        template_type: {status: 0 for status in ('requested', 'delivered', 'failed')}
        for template_type in TEMPLATE_TYPES
    }


def _update_statuses_from_row(
    update_dict,
    row,
):
    if row.status != 'cancelled':
        update_dict['requested'] += row.count
    if row.status in ('delivered', 'sent'):
        update_dict['delivered'] += row.count
    elif row.status in (
        'failed',
        'temporary-failure',
        'permanent-failure',
        'validation-failed',
        'virus-scan-failed',
    ):
        update_dict['failed'] += row.count


def create_empty_monthly_notification_status_stats_dict(year):
    utc_month_starts = get_months_for_financial_year(year)
    # nested dicts - data[month][template type][status] = count
    return {
        convert_utc_to_local_timezone(start).strftime('%Y-%m'): {
            template_type: defaultdict(int) for template_type in TEMPLATE_TYPES
        }
        for start in utc_month_starts
    }
