"""Utiliser exclusivement une base dédiée vide, dont le nom contient ariadne_test."""
import os
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def pg_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL absent : PostgreSQL réel requis")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or "ariadne_test" not in (parsed.database or ""):
        pytest.fail("La base de test doit être PostgreSQL et contenir ariadne_test dans son nom")
    engine = create_engine(url)
    if inspect(engine).get_table_names():
        pytest.fail("La base de test doit être vide pour vérifier les migrations aller/retour")
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    yield engine
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        connection.exec_driver_sql("DROP TABLE alembic_version")
    engine.dispose()


@pytest.fixture
def db(pg_engine):
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
