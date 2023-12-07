from app import db
from app.models import ServiceWhitelist
from sqlalchemy import delete, select


def dao_fetch_service_whitelist(service_id):
    stmt = select(ServiceWhitelist).where(ServiceWhitelist.service_id == service_id)
    return db.session.scalars(stmt).all()


def dao_add_and_commit_whitelisted_contacts(objs):
    db.session.add_all(objs)
    db.session.commit()


def dao_remove_service_whitelist(service_id):
    stmt = delete(ServiceWhitelist).where(ServiceWhitelist.service_id == service_id)
    db.session.execute(stmt)
