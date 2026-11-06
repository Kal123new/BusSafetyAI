"""Recurring school-day service plans and unique daily runs."""
from alembic import op
import sqlalchemy as sa
revision = "0005_service_plans"
down_revision = "0004_bus_driver"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("service_plans", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.Float(), nullable=False), sa.Column("name", sa.String(100), nullable=False),
        sa.Column("bus_id", sa.String(36), sa.ForeignKey("buses.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False), sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.String(500), nullable=True))
    op.create_table("scheduled_runs", sa.Column("plan_id", sa.String(36), sa.ForeignKey("service_plans.id"), primary_key=True),
        sa.Column("service_date", sa.String(10), primary_key=True),
        sa.Column("trip_id", sa.String(36), sa.ForeignKey("trips.id"), nullable=False, unique=True))

def downgrade():
    op.drop_table("scheduled_runs")
    op.drop_table("service_plans")
