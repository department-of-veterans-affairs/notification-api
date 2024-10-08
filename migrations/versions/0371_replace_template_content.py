"""
Revision ID: 371_replace_template_content
Revises: 0370_notification_callback_url
Create Date: 2024-10-08 20:35:38
"""
from alembic import op

revision = '371_replace_template_content'
down_revision = '0370_notification_callback_url'

def upgrade():
    # Replace only the URLs in the 'templates' table
    op.execute("""
        UPDATE templates
        SET content = REPLACE(content, 'https://notification.alpha.canada.ca', 'https://api.va.gov/vanotify')
    """)

    # Replace only the URLs in the 'templates_history' table
    op.execute("""
        UPDATE templates_history
        SET content = REPLACE(content, 'https://notification.alpha.canada.ca', 'https://api.va.gov/vanotify')
    """)


def downgrade():
    # Reverse the replacement of URLs in the 'templates' table
    op.execute("""
        UPDATE templates
        SET content = REPLACE(content, 'https://api.va.gov/vanotify', 'https://notification.alpha.canada.ca')
    """)

    # Reverse the replacement of URLs in the 'templates_history' table
    op.execute("""
        UPDATE templates_history
        SET content = REPLACE(content, 'https://api.va.gov/vanotify', 'https://notification.alpha.canada.ca')
    """)
