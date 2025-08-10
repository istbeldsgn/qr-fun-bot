import os
print("DB_HOST:", os.environ.get("DB_HOST"))
print("DB_PORT:", os.environ.get("DB_PORT"))
print("DB_NAME:", os.environ.get("DB_NAME"))
print("DB_USER:", os.environ.get("DB_USER"))
import os
import sys
import telebot
from telebot.types import InputMediaPhoto, InputMediaVideo
from ticket_generator import generate_ticket_video, generate_ticket


from routes import routes_bus, routes_trolleybus


from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, Update
from flask import Flask, request  # для вебхука (если дальше подключаешь)

import logging
telebot.logger.setLevel(logging.INFO)

from db_store import _conn
try:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("select 1;")
    print("✅ DB OK: подключение установлено")
except Exception as e:
    print(f"❌ DB FAIL: {e}")
    sys.exit(1)

with _conn() as conn, conn.cursor() as cur:
    cur.execute("select current_user, inet_server_addr();")
    print("DB who/where:", cur.fetchone())
    
from db_store import init_db, ensure_admin, load_allowed_and_guest, add_or_update_user, remove_user
from ticket_generator import generate_ticket  # ← твоя функция генерации


def is_allowed(uid: int) -> bool:
    # 1) Быстрая проверка по памяти
    if uid in allowed_users:
        return True
    # 2) Фолбэк: смотрим в БД и если найден — добавляем в память
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("select 1 from public.allowed_users where user_id = %s limit 1;", (uid,))
            ok = cur.fetchone() is not None
        if ok:
            allowed_users.add(uid)
        return ok
    except Exception as e:
        print(f"⚠️ DB check failed: {e}", flush=True)
        return False


from collections import defaultdict, deque
from threading import RLock
import time

last_msgs = defaultdict(deque)
MAX_MSGS = 6          # не более 6 сообщений
WINDOW  = 10          # за 10 секунд

def allow_message(uid: int) -> bool:
    now = time.time()
    q = last_msgs[uid]
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= MAX_MSGS:
        return False
    q.append(now)
    return True

user_locks = defaultdict(RLock)

def with_user_lock(uid: int, timeout: float = 5.0):
    lock = user_locks[uid]
    class _Ctx:
        def __enter__(self):
            self.acquired = lock.acquire(timeout=timeout)
            return self.acquired
        def __exit__(self, exc_type, exc, tb):
            if self.acquired:
                lock.release()
    return _Ctx()


# --- Читаем переменные окружения с понятными ошибками ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID_RAW = os.environ.get("ADMIN_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # пригодится далее для вебхука

missing = []
if not BOT_TOKEN:
    missing.append("BOT_TOKEN")
if not ADMIN_ID_RAW:
    missing.append("ADMIN_ID")
# если прямо сейчас делаешь вебхук, то WEBHOOK_URL обязателен:
if not WEBHOOK_URL:
    missing.append("WEBHOOK_URL")

if missing:
    sys.exit(f"❌ Не заданы переменные окружения: {', '.join(missing)}")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    sys.exit("❌ ADMIN_ID должен быть целым числом")

# --- Инициализируем БД и подгружаем списки из БД ---
init_db()
ensure_admin(ADMIN_ID)  # гарантируем, что админ есть в таблице
allowed_users, guest_users = load_allowed_and_guest()
allowed_users.add(ADMIN_ID)  # на всякий случай держим админа в памяти

# --- Создаём бота ---
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# --- Память для состояний диалога (ключ — user_id, а не chat_id) ---
user_data = {}



from html import escape

def notify_admin_about_access_request(user):
    user_id = user.id
    username = escape(user.username) if user.username else "нет username"
    first_name = escape(user.first_name) if user.first_name else ""
    last_name = escape(user.last_name) if user.last_name else ""
    full_name = f"{first_name} {last_name}".strip()

    text = (
        f"👤 Пользователь пытается получить доступ к боту:\n"
        f"Имя: {full_name}\n"
        f"Username: @{username}\n"
        f"ID: {user_id}\n"
        f'<a href="tg://user?id={user_id}">Профиль</a>\n\n'
        "Предоставить доступ?"
    )

    keyboard = InlineKeyboardMarkup(row_width=2)
    allow_button = InlineKeyboardButton(text="✅ Разрешить", callback_data=f"allow_{user_id}")
    deny_button = InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_{user_id}")
    keyboard.add(allow_button, deny_button)

    bot.send_message(ADMIN_ID, text, reply_markup=keyboard, parse_mode="HTML")


# Обработчик сообщений от НЕ разрешённых пользователей (только личные чаты)
@bot.message_handler(func=lambda m: getattr(m.chat, "type", "") == "private" and not is_allowed(m.from_user.id))
def handle_unauthorized(message):
    user = message.from_user
    bot.send_message(message.chat.id, "⛔ Доступ запрещён. Ожидайте подтверждения от администратора.")
    notify_admin_about_access_request(user)
     
# Блокируем группы, чтобы бот работал только в личке
@bot.message_handler(func=lambda m: getattr(m.chat, "type", "") != "private")
def block_groups(message: Message):
    bot.reply_to(message, "Бот работает только в личных сообщениях. Напишите мне в личку.")
     
@bot.callback_query_handler(func=lambda call: call.data.startswith(("allow_", "deny_")))
def callback_access_control(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для этого действия.")
        return

    if call.data.startswith("allow_"):
        if user_id not in allowed_users:
            allowed_users.add(user_id)
        # если используешь БД (Supabase)
        try:
            add_or_update_user(user_id, role="guest")  # или "user"
        except Exception:
            pass

        bot.answer_callback_query(call.id, "Доступ предоставлен")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Доступ для пользователя [id={user_id}](tg://user?id={user_id}) предоставлен.",
            parse_mode="Markdown"
        )
        try:
            bot.send_message(user_id, "✅ Вам предоставлен доступ к боту. Можете пользоваться.")
        except Exception:
            pass

    else:  # deny_
        if user_id in allowed_users:
            allowed_users.discard(user_id)
        try:
            remove_user(user_id)
        except Exception:
            pass

        bot.answer_callback_query(call.id, "Доступ отклонён")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"❌ Доступ для пользователя [id={user_id}](tg://user?id={user_id}) отклонён.",
            parse_mode="Markdown"
        )
        try:
            bot.send_message(user_id, "❌ К сожалению, доступ к боту вам не предоставлен.")
        except Exception:
            pass


@bot.message_handler(commands=['add_guest'])
def add_guest(message: Message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет прав для выполнения этой команды.")
        return

    if not message.reply_to_message:
        bot.send_message(message.chat.id, "❗ Перешлите сообщение пользователя и ответьте на него командой /add_guest.")
        return

    fwd = message.reply_to_message.forward_from
    guest_id = fwd.id if fwd else None
    if not guest_id:
        bot.send_message(message.chat.id, "⚠️ Не удалось получить ID пользователя. Убедитесь, что он не скрывает пересылку сообщений.")
        return

    allowed_users.add(guest_id)
    guest_users.add(guest_id)
    try:
        add_or_update_user(guest_id, role="guest")
    except Exception:
        pass

    bot.send_message(message.chat.id, f"✅ Пользователь с ID {guest_id} добавлен как гость.")




# Команда /start для разрешённых пользователей — выбор типа транспорта
@bot.message_handler(commands=['start'])
def start(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        bot.send_message(message.chat.id, "⛔ Доступ запрещён. Обратитесь к администратору.")
        return

    bot.send_message(message.chat.id, "Выберите тип транспорта:\n1. Автобус\n2. Троллейбус")
    user_data[uid] = {}


# Обработка текста от разрешённых пользователей для диалога
@bot.message_handler(func=lambda m: getattr(m, "chat", None)
                                  and getattr(m.chat, "type", "") == "private"
                                  and getattr(m, "text", None)
                                  and not m.text.startswith("/"))
def handle_message(message: Message):
    uid = message.from_user.id
    print(f"💬 msg from {uid} allowed={is_allowed(uid)} text={message.text!r}", flush=True)
    
    if not allow_message(uid):
        bot.send_message(message.chat.id, "Слишком много сообщений. Подождите пару секунд 🙏")
        return
        
    if not is_allowed(uid):
        bot.send_message(message.chat.id, "⛔ Доступ запрещён. Обратитесь к администратору.")
        return

    if uid not in user_data:
        user_data[uid] = {}
    data = user_data[uid]

    # 1) Выбор типа транспорта
    if 'transport_type' not in data:
        text = (message.text or "").strip().lower()
        if text in ('1', 'автобус'):
            data['transport_type'] = 'bus'
            bot.send_message(message.chat.id, "Введите номер маршрута (например, 12):")
        elif text in ('2', 'троллейбус'):
            data['transport_type'] = 'trolleybus'
            bot.send_message(message.chat.id, "Введите номер маршрута (например, 2):")
        else:
            bot.send_message(
                message.chat.id,
                "Введите тип транспорта:\n"
                "1. Автобус\n"
                "2. Троллейбус\n"
                "(можно ввести цифру или слово)"
            )

    # 2) Номер маршрута
    elif 'route_num' not in data:
        data['route_num'] = (message.text or "").strip().lower().replace('a', 'а')  # лат. a → кир. а
        route_num = data['route_num']

        route_base = routes_bus if data['transport_type'] == 'bus' else routes_trolleybus
        if route_num in route_base:
            data['directions'] = route_base[route_num]
            bot.send_message(
                message.chat.id,
                f"Выберите направление:\n1. {data['directions'][0]}\n2. {data['directions'][1]}"
            )
        else:
            data['route_manual'] = True
            data['route'] = route_num
            bot.send_message(message.chat.id, "Маршрут не найден, введите гаражный номер:")

    # 3) Направление (если маршрут найден)
    elif 'route' not in data and not data.get('route_manual', False):
        choice = (message.text or "").strip()
        if choice == '1':
            data['route'] = data['directions'][0]
            bot.send_message(message.chat.id, "Введите гаражный номер:")
        elif choice == '2':
            data['route'] = data['directions'][1]
            bot.send_message(message.chat.id, "Введите гаражный номер:")
        else:
            bot.send_message(message.chat.id, "Некорректный ввод. Введите 1 или 2:")

    # 4) Гаражный номер → генерим картинку+видео и шлём альбомом
    elif 'garage_number' not in data:
        data['garage_number'] = (message.text or "").strip()

        transport_label = 'Автобус' if data['transport_type'] == 'bus' else 'Троллейбус'
        img_path = None
        video_path = None
        ticket_path = None
        try:
            # пробуем сделать и картинку, и видео
            img_path, video_path = generate_ticket_video(
                transport_label,
                data['route_num'],
                data['route'],
                data['garage_number'],
                base_video="anim.mp4",   # файл-образец лежит в корне проекта
                crop_top_px=200
            )

            # отправляем альбом: фото + видео
            with open(img_path, 'rb') as f_photo, open(video_path, 'rb') as f_video:
                media = [
                    InputMediaPhoto(f_photo, caption="Ваш билет 🎟️"),
                    InputMediaVideo(f_video),
                ]
                bot.send_media_group(message.chat.id, media)

            bot.send_message(message.chat.id, "✅ Билет сгенерирован! Введите любой символ для нового билета.")

        except Exception as e:
            # фолбэк: хотя бы картинку
            try:
                ticket_path = generate_ticket(
                    transport_label,
                    data['route_num'],
                    data['route'],
                    data['garage_number']
                )
                with open(ticket_path, 'rb') as f:
                    bot.send_photo(message.chat.id, f, caption="Ваш билет 🎟️ (видео временно недоступно)")
            except Exception as e2:
                bot.send_message(message.chat.id, f"Ошибка при генерации билета: {e2}")

        finally:
            # очистка временных файлов
            for p in (img_path, video_path, ticket_path):
                if p:
                    try: os.remove(p)
                    except Exception: pass

            user_data.pop(uid, None)

    # 5) Защитный fallback
    else:
        bot.send_message(
            message.chat.id,
            "❗ Неожиданное сообщение. Вы можете:\n"
            "🔄 Ввести любой символ, чтобы начать заново\n"
            "📌 Или нажмите /start, чтобы снова выбрать тип транспорта"
        )
        user_data.pop(uid, None)


        
#заменил polling , делаю вебхук 
# --- Вебхук (Flask) ---
from flask import Flask, request
from telebot.types import Update

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    # чтобы Render не видел 404 на корне
    return "ok", 200

@app.route("/healthz", methods=["GET"])
def health():
    return "ok", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data().decode("utf-8")
    print("⬇️ update:", raw, flush=True)   # видно любой апдейт
    try:
        upd = Update.de_json(raw)
        bot.process_new_updates([upd])
    except Exception as e:
        print("🔥 webhook handler error:", repr(e), flush=True)
    return "OK", 200

def configure_webhook():
    # ставим вебхук и при gunicorn, и при python
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL, allowed_updates=["message", "callback_query"])
    # необязательно, но полезно: проверка, что токен рабочий
    try:
        me = bot.get_me()
        print(f"✅ Telegram OK: @{me.username} (id {me.id})")
    except Exception as e:
        print(f"❌ Telegram auth failed: {e}")
        sys.exit(1)

# вызываем сразу при импорте модуля (важно для gunicorn)
configure_webhook()

if __name__ == "__main__":
    # при локальном запуске/polling-free — поднимем встроенный сервер Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


















