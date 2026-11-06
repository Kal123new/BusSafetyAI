"""Preserve unavailable browser speed as unknown, never zero."""
from alembic import op
import sqlalchemy as sa

revision = "0003_unknown_gps_speed"
down_revision = "0002_postgis"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("location_samples") as batch:
        batch.alter_column("speed_mps", existing_type=sa.Float(), nullable=True)


def downgrade():
    # Unknown historical speeds cannot safely be invented as zero.
    raise RuntimeError("Cannot remove unknown-speed support without an explicit data migration")
