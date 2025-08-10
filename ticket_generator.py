# ticket_generator.py
import os
import uuid
import tempfile
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import pytz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

def _tmp_path(ext: str) -> str:
    """Уникальный файл во /tmp, чтобы не конфликтовать при параллельной работе."""
    return os.path.join(
        tempfile.gettempdir(),
        f"ticket_{uuid.uuid4().hex[:12]}.{ext.lstrip('.')}"
    )

def _load_font(filename: str, size: int) -> ImageFont.FreeTypeFont:
    """Пытаемся загрузить TTF, при ошибке — системный шрифт по умолчанию."""
    path = os.path.join(FONTS_DIR, filename)
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        # запасной вариант
        return ImageFont.load_default()

# Грузим шрифты один раз (быстрее и экономнее по памяти)
FONT_TRANSPORT = _load_font("TTNormsPro-Medium.ttf", 54)
FONT_ROUTE     = _load_font("TTNormsPro-Medium.ttf", 41)
FONT_REGULAR   = _load_font("TTNormsPro-Normal.ttf", 48)

def generate_ticket(transport: str, number: str, route: str, garage_number: str) -> str:
    """
    Рисует билет на основе template.jpg и возвращает путь к сгенерированному JPG во /tmp.
    """
    template_path = os.path.join(BASE_DIR, "template.jpg")
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Не найден шаблон: {template_path}")

    img = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Дата/время (Минск)
    minsk_time = datetime.now(pytz.timezone("Europe/Minsk"))
    date_text = minsk_time.strftime("%d.%m.%Y")
    time_text = minsk_time.strftime("%H:%M:%S")

    # ==== Заголовок: «Автобус №12» — центр по x=585, y=506 ====
    title = f"{transport} №{number}"
    bbox = FONT_TRANSPORT.getbbox(title)
    title_w = bbox[2] - bbox[0]
    draw.text((585 - title_w / 2, 506), title, font=FONT_TRANSPORT, fill="black")

    # ==== Маршрут — центр по x=585, y=712 ====
    bbox = FONT_ROUTE.getbbox(route)
    route_w = bbox[2] - bbox[0]
    draw.text((585 - route_w / 2, 712), route, font=FONT_ROUTE, fill="black")

    # ==== Гаражный номер + подчёркивание ====
    garage_x, garage_y = 98, 950
    draw.text((garage_x, garage_y), garage_number, font=FONT_REGULAR, fill="black")
    gb = FONT_REGULAR.getbbox(garage_number)
    g_w = gb[2] - gb[0]
    g_h = gb[3] - gb[1]
    underline_y = garage_y + g_h + 20
    draw.line((garage_x, underline_y, garage_x + g_w, underline_y), fill="black", width=2)

    # ==== Дата (слева) ====
    draw.text((98, 1072), date_text, font=FONT_REGULAR, fill="black")

    # ==== Время (справа) — подгоняем по ширине ====
    tb = FONT_REGULAR.getbbox(time_text)
    time_w = tb[2] - tb[0]
    draw.text((1077 - time_w, 1072), time_text, font=FONT_REGULAR, fill="black")

    # Сохраняем в /tmp и возвращаем путь
    out_img = _tmp_path("jpg")
    img.save(out_img, format="JPEG", quality=95, optimize=True)
    return out_img
