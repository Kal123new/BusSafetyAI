"""PostGIS generated geography points for indexed geographic queries."""
from alembic import op

revision = "0002_postgis"
down_revision = "30b84ab90d4d"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        for table in ("stops", "trip_stops"):
            op.execute(f"ALTER TABLE {table} ADD COLUMN location geography(Point,4326) "
                       "GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography) STORED")
            op.execute(f"CREATE INDEX {table}_location_gist ON {table} USING GIST(location)")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in ("trip_stops", "stops"):
            op.execute(f"DROP INDEX {table}_location_gist")
            op.execute(f"ALTER TABLE {table} DROP COLUMN location")
