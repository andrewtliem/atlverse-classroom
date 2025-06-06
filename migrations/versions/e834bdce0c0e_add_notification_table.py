"""Add notification table

Revision ID: e834bdce0c0e
Revises: ba4fcc97d4fe
Create Date: 2025-06-06 05:02:57.732640

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e834bdce0c0e'
down_revision = 'ba4fcc97d4fe'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('message', sa.String(length=255), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=True, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('notification')
