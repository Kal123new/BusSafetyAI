"""Preserve the chain of custody for exceptional replacement-bus runs."""
from alembic import op
import sqlalchemy as sa
revision = '0006_passenger_transfers'
down_revision = '0005_service_plans'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('passenger_transfers',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('source_trip_id',sa.String(36),sa.ForeignKey('trips.id'),nullable=False),
        sa.Column('target_trip_id',sa.String(36),sa.ForeignKey('trips.id'),nullable=False),
        sa.Column('student_id',sa.String(36),sa.ForeignKey('students.id'),nullable=False),
        sa.Column('previous_status',sa.String(20),nullable=False),sa.Column('reason',sa.String(500),nullable=False),
        sa.Column('actor_id',sa.String(100),nullable=False),sa.UniqueConstraint('source_trip_id','student_id'))
    op.create_index('ix_transfer_source','passenger_transfers',['source_trip_id'])
    op.create_index('ix_transfer_target','passenger_transfers',['target_trip_id'])

def downgrade():
    op.drop_table('passenger_transfers')
