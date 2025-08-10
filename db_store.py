# db_store.py
import os
import sys
import socket
import psycopg2
from typing import Set, Tuple


def _require(name: str) -> str:
    """Читает обязательную переменную окружения или падает с понятной ошибкой."""
    val = os.environ.get(name)
    if not val:
        sys.exit(f"❌ Переменная окружения {name} не задана")
    return val


def _conn():
    """
    Подключение к Postgres через отдельные переменные окружения.
    Делает быструю попытку обычного подключения и fallback на IPv4,
    если среда пытается идти по IPv6 и он недоступен (Render free).
    """
    host = _require("DB_HOST")
    port_str = os.environ.get("DB_PORT", "5432")
    try:
        port = int(port_str)
    except ValueError:
        sys.exit("❌ DB_PORT должен быть числом")
    name = _require("DB_NAME")
    user = _require("DB_USER")
    pwd  = _require("DB_PASSWORD")

    # 1) Обычная попытка (если DNS вернёт IPv4 — сразу ок)
    try:
        return psycopg2.connect(
            host=host,
            port=port,
            dbname=name,
            user=user,
            password=pwd,
            sslmode="require",
            connect_timeout=5,
            application_name="transport-bot",
        )
    except psycopg2.OperationalError:
        # 2) Fallback: принудительно берём IPv4 и подключаемся через hostaddr
        try:
            ipv4 = next(ai[4][0] for ai in socket.getaddrinfo(
                host, port, socket.AF_INET, socket.SOCK_STREAM
            ))
        except StopIteration:
            # IPv4 не найден — поднимем исходную ошибку
            raise

        return psycopg2.connect(
            host=host,          # важно оставить для TLS/SNI
            hostaddr=ipv4,      # реальный IPv4-адрес
            port=port,
            dbname=name,
            user=user,
            password=pwd,
            sslmode="require",
            connect_timeout=5,
            application_name="transport-bot(v4)",
        )


def init_db() -> None:
    """Создаёт таблицу и индексы, если их ещё нет."""
    sql = """
    create table if not exists public.allowed_users (
      user_id   bigint primary key,
      role      text not null check (role in ('admin','user','guest')),
      added_at  timestamptz not null default now()
    );

    create index if not exists idx_allowed_users_role
      on public.allowed_users(role);
    """
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql)


def ensure_admin(admin_id: int) -> None:
    """Гарантируем, что админ есть в таблице (role='admin')."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into public.allowed_users (user_id, role)
            values (%s, 'admin')
            on conflict (user_id) do update
              set role = excluded.role, added_at = now();
            """,
            (admin_id,),
        )


def load_allowed_and_guest() -> Tuple[Set[int], Set[int]]:
    """Возвращает множества: (allowed_users, guest_users)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("select user_id, role from public.allowed_users;")
        rows = cur.fetchall()
    allowed, guests = set(), set()
    for uid, role in rows:
        allowed.add(int(uid))
        if (role or "").lower() == "guest":
            guests.add(int(uid))
    return allowed, guests


def add_or_update_user(user_id: int, role: str = "user") -> None:
    """Добавляет или обновляет пользователя с указанной ролью."""
    if role not in ("admin", "user", "guest"):
        role = "user"
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into public.allowed_users (user_id, role)
            values (%s, %s)
            on conflict (user_id) do update
              set role = excluded.role, added_at = now();
            """,
            (user_id, role),
        )


def remove_user(user_id: int) -> None:
    """Удаляет пользователя из таблицы."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "delete from public.allowed_users where user_id = %s;",
            (user_id,),
        )
