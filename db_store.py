# db_store.py
import os, psycopg2

def _conn():
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    name = os.environ["DB_NAME"]
    user = os.environ["DB_USER"]
    pwd  = os.environ["DB_PASSWORD"]
    return psycopg2.connect(
        host=host, port=port, dbname=name, user=user, password=pwd, sslmode="require"
    )

def _conn():
    # гарантируем SSL, если вдруг его нет в строке
    dsn = DATABASE_URL
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return psycopg2.connect(dsn)

def init_db():
    sql = """
    create table if not exists public.allowed_users (
      user_id   bigint primary key,
      role      text not null check (role in ('admin','user','guest')),
      added_at  timestamptz not null default now()
    );
    create index if not exists idx_allowed_users_role on public.allowed_users(role);
    """
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql)

def ensure_admin(admin_id: int):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
        insert into public.allowed_users (user_id, role)
        values (%s, 'admin')
        on conflict (user_id) do update set role = excluded.role, added_at = now();
        """, (admin_id,))

def load_allowed_and_guest():
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("select user_id, role from public.allowed_users;")
        rows = cur.fetchall()
    allowed, guests = set(), set()
    for uid, role in rows:
        allowed.add(uid)
        if (role or "").lower() == "guest":
            guests.add(uid)
    return allowed, guests

def add_or_update_user(user_id: int, role: str = "user"):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
        insert into public.allowed_users (user_id, role)
        values (%s, %s)
        on conflict (user_id) do update
        set role = excluded.role, added_at = now();
        """, (user_id, role))

def remove_user(user_id: int):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("delete from public.allowed_users where user_id = %s;", (user_id,))

