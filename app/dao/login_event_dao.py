from app import db
from app.models import LoginEvent
from sqlalchemy import select

from app.dao.dao_utils import transactional


def list_login_events(user_id):
    stmt = select(LoginEvent).where(LoginEvent.user_id == user_id).order_by(LoginEvent.created_at.desc()).limit(3)
    return db.session.scalars(stmt).all()


@transactional
def save_login_event(login_event):
    db.session.add(login_event)
