from app import db
from app.models import Event


def dao_create_event(event: dict):
    """
    Given a dictionary of event data like . . .
    
    {'event_type': 'sucessful_login', 'data': {'in_fact': 'could be anything', 'something': 'random'}}
    
    . . . persist a new Event instance.
    """

    event_instance = Event(**event)
    db.session.add(event_instance)
    db.session.commit()
