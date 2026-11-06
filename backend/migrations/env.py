from alembic import context

from backend.config import Settings
from backend.db import make_engine
from backend.models import Base

config = context.config
url = config.attributes.get("database_url") or Settings.from_env().database_url

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=engine.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
