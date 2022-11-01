# https://flask-sqlalchemy.palletsprojects.com/en/2.x/api/#flask_sqlalchemy.SQLAlchemy
from flask_sqlalchemy import SQLAlchemy as _SQLAlchemy
from sqlalchemy import MetaData

convention = {
  "ix": "ix_%(column_0_label)s",
  "uq": "uq_%(table_name)s_%(column_0_name)s",
  "ck": "ck_%(table_name)s_%(constraint_name)s",
  "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
  "pk": "pk_%(table_name)s"
}

class SQLAlchemy(_SQLAlchemy):
    """We need to subclass SQLAlchemy in order to override create_engine options"""

    def apply_driver_hacks(self, app, info, options):
        super().apply_driver_hacks(app, info, options)
        if 'connect_args' not in options:
            options['connect_args'] = {}
        options['connect_args']["options"] = "-c statement_timeout={}".format(
            int(app.config['SQLALCHEMY_STATEMENT_TIMEOUT']) * 1000
        )


db = SQLAlchemy(metadata=MetaData(naming_convention=convention))
