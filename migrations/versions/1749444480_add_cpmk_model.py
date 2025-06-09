"""Add cpmk model

Revision ID: 1749444480
Revises: 32b428bffa0f
Create Date: 2025-06-09 12:59:48.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '1749444480'
down_revision = '32b428bffa0f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cpmk',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('classroom_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['classroom_id'], ['classroom.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.add_column('material', sa.Column('cpmk_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'material', 'cpmk', ['cpmk_id'], ['id'])
    op.add_column('quiz', sa.Column('cpmk_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'quiz', 'cpmk', ['cpmk_id'], ['id'])
    op.add_column('assignment', sa.Column('cpmk_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'assignment', 'cpmk', ['cpmk_id'], ['id'])


def downgrade():
    op.drop_constraint(None, 'assignment', type_='foreignkey')
    op.drop_column('assignment', 'cpmk_id')
    op.drop_constraint(None, 'quiz', type_='foreignkey')
    op.drop_column('quiz', 'cpmk_id')
    op.drop_constraint(None, 'material', type_='foreignkey')
    op.drop_column('material', 'cpmk_id')
    op.drop_table('cpmk')
