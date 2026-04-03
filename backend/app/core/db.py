from contextlib import contextmanager
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor
from app.core.config import settings


def _build_connect_kwargs() -> dict:
    parsed = urlparse(settings.database_url)
    return {
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "cursor_factory": RealDictCursor,
    }


@contextmanager
def get_conn():
    conn = psycopg2.connect(**_build_connect_kwargs())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
