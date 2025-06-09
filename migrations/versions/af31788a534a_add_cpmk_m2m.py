"""add association tables for CPMK relations"""
from alembic import op
import sqlalchemy as sa

revision = 'af31788a534a'
down_revision = 'fd787053c267'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'material_cpmk',
        sa.Column('material_id', sa.Integer(), nullable=False),
        sa.Column('cpmk_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['material_id'], ['material.id']),
        sa.ForeignKeyConstraint(['cpmk_id'], ['cpmk.id']),
        sa.PrimaryKeyConstraint('material_id', 'cpmk_id')
    )
    op.create_table(
        'quiz_cpmk',
        sa.Column('quiz_id', sa.Integer(), nullable=False),
        sa.Column('cpmk_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['quiz_id'], ['quiz.id']),
        sa.ForeignKeyConstraint(['cpmk_id'], ['cpmk.id']),
        sa.PrimaryKeyConstraint('quiz_id', 'cpmk_id')
    )
    op.create_table(
        'assignment_cpmk',
        sa.Column('assignment_id', sa.Integer(), nullable=False),
        sa.Column('cpmk_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['assignment_id'], ['assignment.id']),
        sa.ForeignKeyConstraint(['cpmk_id'], ['cpmk.id']),
        sa.PrimaryKeyConstraint('assignment_id', 'cpmk_id')
    )
    with op.batch_alter_table('material', schema=None) as batch_op:
        batch_op.drop_column('cpmk_id')
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.drop_column('cpmk_id')
    with op.batch_alter_table('assignment', schema=None) as batch_op:
        batch_op.drop_column('cpmk_id')


def downgrade():
    with op.batch_alter_table('assignment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpmk_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'cpmk', ['cpmk_id'], ['id'])
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpmk_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'cpmk', ['cpmk_id'], ['id'])
    with op.batch_alter_table('material', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpmk_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'cpmk', ['cpmk_id'], ['id'])
    op.drop_table('assignment_cpmk')
    op.drop_table('quiz_cpmk')
    op.drop_table('material_cpmk')
