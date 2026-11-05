import os
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker


def database_url() -> str | URL:
    return os.getenv("DATABASE_URL") or URL.create(
        "postgresql+psycopg", username=os.getenv("DB_USER", "ariadne"),
        password=os.getenv("DB_PASSWORD", "ariadne_local_only"),
        host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "ariadne"),
    )


engine = create_engine(database_url(), pool_pre_ping=True)
Session = sessionmaker(engine)


def get_session():
    with Session() as session:
        yield session
