from sqlalchemy import select

from app import db
from app.models import UserServiceRoles
from app.model import User


def get_active_business_contact_emails():
    stmt = (
        select(User.email_address)
        .join(UserServiceRoles)
        .where(
            UserServiceRoles.role == 'business_contact',
            User.state == 'active',
        )
        .distinct()
    )

    return db.session.scalars(stmt).all()


def get_active_technical_contact_emails():
    stmt = (
        select(User.email_address)
        .join(UserServiceRoles)
        .where(
            UserServiceRoles.role == 'technical_contact',
            User.state == 'active',
        )
        .distinct()
    )

    return db.session.scalars(stmt).all()


def get_all_active_user_emails():
    stmt = (
        select(User.email_address)
        .where(
            User.state == 'active',
        )
        .distinct()
    )

    return db.session.scalars(stmt).all()
