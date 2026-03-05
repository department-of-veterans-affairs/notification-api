from sqlalchemy import func, select

from app import db
from app.models import UserServiceRoles
from app.model import User


def _lowercase_deduplicate(emails: list[str]) -> list[str]:
    unique_emails = {email.lower() for email in emails}
    return sorted(list(unique_emails))


def get_active_business_contact_emails():
    """Return lowercase distinct email addresses for users with active business_contact role assignments."""
    stmt = (
        select(User.email_address)
        .join(UserServiceRoles)
        .where(
            UserServiceRoles.role == 'business_contact',
            User.state == 'active',
            func.lower(User.email_address).notlike('_archived%'),
        )
        .distinct()
    )

    return _lowercase_deduplicate(db.session.scalars(stmt).all())


def get_active_technical_contact_emails():
    """Return lowercase distinct email addresses for users with active technical_contact role assignments."""
    stmt = (
        select(User.email_address)
        .join(UserServiceRoles)
        .where(
            UserServiceRoles.role == 'technical_contact',
            User.state == 'active',
            func.lower(User.email_address).notlike('_archived%'),
        )
        .distinct()
    )

    return _lowercase_deduplicate(db.session.scalars(stmt).all())


def get_all_active_user_emails():
    """Return lowercase distinct email addresses for all active users regardless of role assignment."""
    stmt = (
        select(User.email_address)
        .where(
            User.state == 'active',
            func.lower(User.email_address).notlike('_archived%'),
        )
        .distinct()
    )

    return _lowercase_deduplicate(db.session.scalars(stmt).all())
