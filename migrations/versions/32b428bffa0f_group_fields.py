"""group fields

Revision ID: 32b428bffa0f
Revises: fd787053c267
Create Date: 2025-06-09 00:28:13.682168

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '32b428bffa0f'
down_revision = 'fd787053c267'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assignment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('allow_group_submission', sa.Boolean(), nullable=True))

    with op.batch_alter_table('assignment_submission', schema=None) as batch_op:
        batch_op.add_column(sa.Column('group_member_ids', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('assignment_submission', schema=None) as batch_op:
        batch_op.drop_column('group_member_ids')

    with op.batch_alter_table('assignment', schema=None) as batch_op:
        batch_op.drop_column('allow_group_submission')
