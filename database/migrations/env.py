"""Alembic environment for the central ANNA hospital database."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from dashboards.common.config import config as anna_config
from dashboards.common.database import Base
import dashboards.common.models  # noqa: F401 - register all SQLAlchemy tables

alembic_config = context.config
if alembic_config.config_file_name:
    fileConfig(alembic_config.config_file_name)
alembic_config.set_main_option("sqlalchemy.url", anna_config.database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=anna_config.database_url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(alembic_config.get_section(alembic_config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
