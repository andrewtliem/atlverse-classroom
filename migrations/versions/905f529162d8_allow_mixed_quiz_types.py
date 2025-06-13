"""allow mixed quiz types

Revision ID: 905f529162d8
Revises: b2d03246b7b6
Create Date: 2025-06-10 11:43:37.539469

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '905f529162d8'
down_revision = 'b2d03246b7b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.alter_column('quiz_type', existing_type=sa.String(length=20), nullable=True)

    with op.batch_alter_table('self_evaluation', schema=None) as batch_op:
        batch_op.alter_column('quiz_type', existing_type=sa.String(length=20), nullable=True)


def downgrade():
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.alter_column('quiz_type', existing_type=sa.String(length=20), nullable=False)

    with op.batch_alter_table('self_evaluation', schema=None) as batch_op:
        batch_op.alter_column('quiz_type', existing_type=sa.String(length=20), nullable=False)
