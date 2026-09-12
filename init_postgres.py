import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='root', dbname='postgres')
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname = 'anna_hospital'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE anna_hospital;")
    print("Created database anna_hospital")
else:
    print("Database anna_hospital already exists")
cur.close()
conn.close()
