"""
Revision ID: 371_replace_template_content
Revises: 0370_notification_callback_url
Create Date: 2024-10-08 20:35:38
"""
from alembic import op

revision = '371_replace_template_content'
down_revision = '0370_notification_callback_url'

def upgrade():
    op.execute("""
        UPDATE templates
        SET content = REPLACE(content, 'https://notification.alpha.canada.ca', 'https://api.va.gov/vanotify')
    """)

    op.execute("""
        UPDATE templates_history
        SET content = REPLACE(content, 'https://notification.alpha.canada.ca', 'https://api.va.gov/vanotify')
    """)


def downgrade():
    op.execute("""
        UPDATE templates
        SET content = REPLACE(content, 'https://api.va.gov/vanotify', 'https://notification.alpha.canada.ca')
    """)

    op.execute("""
        UPDATE templates_history
        SET content = REPLACE(content, 'https://api.va.gov/vanotify', 'https://notification.alpha.canada.ca')
    """)
