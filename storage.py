"""Durable SQL state. PostgreSQL online; SQLite only in the local sandbox."""
import threading
import time
from contextlib import contextmanager
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, JSON, select, text, delete
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

metadata = MetaData()
users = Table('ns_users', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(32), unique=True, nullable=False),
    Column('password_hash', String(256), nullable=False),
    Column('progress', JSON, nullable=False),
    Column('epoch', Integer, nullable=False, default=0),
    Column('active', Integer, nullable=False, default=1),
    Column('created', Float, nullable=False))
limits = Table('ns_limits', metadata,
    Column('key', String(150), primary_key=True),
    Column('count', Integer, nullable=False),
    Column('at', Float, nullable=False))
events = Table('ns_events', metadata,
    Column('id', Integer, primary_key=True),
    Column('actor', String(40), nullable=False),
    Column('action', String(100), nullable=False),
    Column('at', Float, nullable=False))


def blank_progress():
    return {'solves': [], 'hints': [], 'reviewed': False, 'verified': False}


class Store:
    def __init__(self, url):
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        self.postgres = url.startswith('postgresql+')
        if self.postgres:
            parsed = make_url(url)
            if parsed.query.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
                parsed = parsed.update_query_dict({'sslmode': 'require'})
            url = parsed
        args = {'connect_timeout': 10} if self.postgres else {'timeout': 20, 'check_same_thread': False}
        self.engine = create_engine(url, poolclass=NullPool, connect_args=args)
        self.initialized = False
        self.schema_lock = threading.Lock()

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            if not self.postgres:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def initialize(self):
        if self.initialized:
            return
        with self.schema_lock:
            if self.initialized:
                return
            with self.transaction() as conn:
                if self.postgres:
                    conn.execute(text('SELECT pg_advisory_xact_lock(730126419)'))
                metadata.create_all(conn)
            self.initialized = True

    def user(self, uid):
        with self.engine.connect() as conn:
            return conn.execute(select(users).where(users.c.id == uid)).mappings().first()

    def mutate(self, uid, action):
        with self.transaction() as conn:
            query = select(users).where(users.c.id == uid)
            if self.postgres:
                query = query.with_for_update()
            row = conn.execute(query).mappings().one()
            progress = dict(row['progress'])
            result = action(progress, row)
            conn.execute(users.update().where(users.c.id == uid).values(progress=progress))
            return result

    def limit(self, key, maximum, seconds=60):
        now = time.time()
        bucket = f'{key}:{int(now // seconds)}'
        insert = pg_insert if self.postgres else sqlite_insert
        with self.transaction() as conn:
            statement = insert(limits).values(key=bucket, count=1, at=now)
            statement = statement.on_conflict_do_update(index_elements=[limits.c.key], set_={'count': limits.c.count + 1})
            count = conn.execute(statement.returning(limits.c.count)).scalar_one()
            conn.execute(delete(limits).where(limits.c.at < now - 7200))
        return count <= maximum

    def audit(self, actor, action):
        with self.engine.begin() as conn:
            conn.execute(events.insert().values(actor=actor, action=action, at=time.time()))
