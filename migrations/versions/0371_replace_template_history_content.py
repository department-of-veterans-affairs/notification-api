"""
Revision ID: 371_replace_template_history_content
Revises: 0370_notification_callback_url
Create Date: 2024-10-08 20:35:38
"""
from alembic import op
from sqlalchemy import text

revision = '371_replace_template_history_content'
down_revision = '0370_notification_callback_url'

def upgrade():
    op.execute(
        text("""
            UPDATE templates_history
            SET name = REPLACE(name, :old_name, :new_name),
                content = REPLACE(content, :old_url, :new_url)
        """),
        {"old_name": "GOV.UK", "new_name": "", 
         "old_url": "https://notification.alpha.canada.ca", 
         "new_url": "https://api.va.gov/vanotify"}
    )

def downgrade():
    op.execute(
        text("""
            UPDATE templates_history
            SET content = REPLACE(content, :new_url, :old_url)
        """),
        {"old_url": "https://notification.alpha.canada.ca", 
         "new_url": "https://api.va.gov/vanotify"}
    )
