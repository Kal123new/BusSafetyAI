"""Save a default driver without changing historical trip assignments."""
from alembic import op
import sqlalchemy as sa
revision = "0004_bus_driver"
down_revision = "0003_unknown_gps_speed"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("buses", table_args=(sa.CheckConstraint("passenger_capacity > 0", name="ck_bus_capacity"),) if op.get_bind().dialect.name == "sqlite" else ()) as batch:
        batch.add_column(sa.Column("default_driver_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_bus_default_driver", "drivers", ["default_driver_id"], ["id"])

def downgrade():
    with op.batch_alter_table("buses", table_args=(sa.CheckConstraint("passenger_capacity > 0", name="ck_bus_capacity"),) if op.get_bind().dialect.name == "sqlite" else ()) as batch:
        batch.drop_constraint("fk_bus_default_driver", type_="foreignkey")
        batch.drop_column("default_driver_id")
