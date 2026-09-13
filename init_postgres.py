import os
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

conn = psycopg2.connect(
    host=os.environ.get('POSTGRES_HOST', 'localhost'),
    port=int(os.environ.get('POSTGRES_PORT', '5432')),
    user=os.environ.get('POSTGRES_ADMIN_USER', 'postgres'),
    password=os.environ['POSTGRES_ADMIN_PASSWORD'],
    dbname='postgres',
)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
database_name = os.environ.get('POSTGRES_DB', 'anna_hospital')
cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
if not cur.fetchone():
    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    print(f"Created database {database_name}")
else:
    print(f"Database {database_name} already exists")
cur.close()
conn.close()
