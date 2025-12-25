import os
import sys
import time
from collections import defaultdict, deque
from threading import RLock

import telebot
from telebot.types import Message, Update
from flask import Flask, request

from routes import routes_bus, routes_trolleybus
from ticket_generator import generate_ticket


# ----------------- ENV -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

missing = []
if not BOT_TOKEN:
    missing.append("BOT_TOKEN")
if not WEBHOOK_URL:
    missing.append("WEBHOOK_URL")
if missing:
    sys.exit(f"❌ Не заданы переменные окружения: {', '.join(missing)}")


# ----------------- Bot -----------------
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ----------------- State (FSM) -----------------
user_data = {}  # user_id -> dict


# ----------------- Anti-flood -----------------
last_msgs = defaultdict(deque)
MAX_MSGS = 6
WINDOW = 10

def allow_message(uid: int) -> bool:
    now = time.time()
    q = last_msgs[uid]
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= MAX_MSGS:
        return False
    q.append(now)
    return True


# ----------------- Locks per user -----------------
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


def safe_send(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print("🔥 send error:", repr(e), flush=True)
        return None


def compact_user(user) -> str:
    username = f"@{user.username}" if getattr(user, "username", None) else "-"
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    full = (first + " " + last).strip() or "-"
    uid = getattr(user, "id", "-")
    return f"{username} | {full} | id={uid}"


def log_ticket_generated(user, payload: dict):
    # короткая строка для Render
    print(
        "🎟️ ticket_generated "
        f"user={compact_user(user)} "
        f"transport={payload.get('transport_label')} "
        f"route_num={payload.get('route_num')} "
        f"route={payload.get('route')} "
        f"garage={payload.get('garage_number')}",
        flush=True
    )


# ----------------- Commands -----------------
@bot.message_handler(commands=['start'])
def start(message: Message):
    uid = message.from_user.id
    user_data[uid] = {}
    safe_send(bot.send_message, message.chat.id, "Выберите тип транспорта:\n1. Автобус\n2. Троллейбус")


# Блокируем группы — бот работает только в личке
@bot.message_handler(func=lambda m: getattr(m.chat, "type", "") != "private")
def block_groups(message: Message):
    safe_send(bot.reply_to, message, "Бот работает только в личных сообщениях. Напишите мне в личку.")


# ----------------- Main dialog handler -----------------
@bot.message_handler(
    func=lambda m: getattr(m, "chat", None)
    and getattr(m.chat, "type", "") == "private"
    and getattr(m, "text", None)
    and not m.text.startswith("/")
)
def handle_message(message: Message):
    uid = message.from_user.id

    if not allow_message(uid):
        safe_send(bot.send_message, message.chat.id, "Слишком много сообщений. Подождите пару секунд 🙏")
        return

    if uid not in user_data:
        user_data[uid] = {}
    data = user_data[uid]

    with with_user_lock(uid) as acquired:
        if not acquired:
            safe_send(bot.send_message, message.chat.id, "Подождите секунду и повторите 🙏")
            return

        try:
            # 1) Выбор типа транспорта
            if 'transport_type' not in data:
                text = (message.text or "").strip().lower()
                if text in ('1', 'автобус'):
                    data['transport_type'] = 'bus'
                    safe_send(bot.send_message, message.chat.id, "Введите номер маршрута (например, 12):")
                elif text in ('2', 'троллейбус'):
                    data['transport_type'] = 'trolleybus'
                    safe_send(bot.send_message, message.chat.id, "Введите номер маршрута (например, 2):")
                else:
                    safe_send(
                        bot.send_message,
                        message.chat.id,
                        "Введите тип транспорта:\n1. Автобус\n2. Троллейбус\n(можно ввести цифру или слово)"
                    )
                return

            # 2) Номер маршрута
            if 'route_num' not in data:
                data['route_num'] = (message.text or "").strip().lower().replace('a', 'а')
                route_num = data['route_num']

                route_base = routes_bus if data['transport_type'] == 'bus' else routes_trolleybus
                if route_num in route_base:
                    data['directions'] = route_base[route_num]
                    safe_send(
                        bot.send_message,
                        message.chat.id,
                        f"Выберите направление:\n1. {data['directions'][0]}\n2. {data['directions'][1]}"
                    )
                else:
                    data['route_manual'] = True
                    data['route'] = route_num
                    safe_send(bot.send_message, message.chat.id, "Маршрут не найден, введите гаражный номер:")
                return

            # 3) Направление (если маршрут найден)
            if 'route' not in data and not data.get('route_manual', False):
                choice = (message.text or "").strip()
                if choice == '1':
                    data['route'] = data['directions'][0]
                    safe_send(bot.send_message, message.chat.id, "Введите гаражный номер:")
                elif choice == '2':
                    data['route'] = data['directions'][1]
                    safe_send(bot.send_message, message.chat.id, "Введите гаражный номер:")
                else:
                    safe_send(bot.send_message, message.chat.id, "Некорректный ввод. Введите 1 или 2:")
                return

            # 4) Гаражный номер → генерим фото и отправляем
            if 'garage_number' not in data:
                data['garage_number'] = (message.text or "").strip()

                transport_label = 'Автобус' if data['transport_type'] == 'bus' else 'Троллейбус'
                img_path = None

                payload = {
                    "transport_label": transport_label,
                    "route_num": data.get("route_num"),
                    "route": data.get("route"),
                    "garage_number": data.get("garage_number"),
                }

                try:
                    img_path = generate_ticket(
                        transport_label,
                        data['route_num'],
                        data['route'],
                        data['garage_number']
                    )

                    # отправляем фото как документ (стабильнее, чем photo)
                    with open(img_path, 'rb') as f:
                        safe_send(bot.send_document, message.chat.id, f, caption="Ваш билет 🎟️")

                    # лог в Render — только после успешной выдачи
                    log_ticket_generated(message.from_user, payload)

                    safe_send(bot.send_message, message.chat.id, "✅ Готово! Введите любой символ для нового билета.")
                except Exception as e:
                    safe_send(bot.send_message, message.chat.id, f"Ошибка при генерации: {e}")
                    print("🔥 ticket generation error:", repr(e), flush=True)
                finally:
                    if img_path:
                        try:
                            os.remove(img_path)
                        except Exception:
                            pass
                    user_data.pop(uid, None)
                return

            # 5) fallback
            safe_send(
                bot.send_message,
                message.chat.id,
                "❗ Неожиданное сообщение. Вы можете:\n"
                "🔄 Ввести любой символ, чтобы начать заново\n"
                "📌 Или нажмите /start, чтобы снова выбрать тип транспорта"
            )
            user_data.pop(uid, None)

        except Exception as e:
            print("🔥 handler fatal error:", repr(e), flush=True)
            safe_send(bot.send_message, message.chat.id, "Произошла ошибка. Нажмите /start и попробуйте снова.")
            user_data.pop(uid, None)
# ----------------- Webhook (Flask) -----------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "ok", 200

@app.route("/healthz", methods=["GET"])
def health():
    return "ok", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data().decode("utf-8")
    try:
        upd = Update.de_json(raw)
        bot.process_new_updates([upd])
    except Exception as e:
        print("🔥 webhook handler error:", repr(e), flush=True)
    return "OK", 200


def configure_webhook():
    # важно для Render: выставляем вебхук при старте контейнера
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL, allowed_updates=["message"])
    try:
        me = bot.get_me()
        print(f"✅ Telegram OK: @{me.username} (id {me.id})", flush=True)
        print(f"✅ Webhook set: {WEBHOOK_URL}", flush=True)
    except Exception as e:
        print(f"❌ Telegram auth failed: {e}", flush=True)
        sys.exit(1)


# вызываем при импорте — работает
