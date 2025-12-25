import os
import random
import uuid
import tempfile
from datetime import datetime

import pytz
from PIL import Image, ImageDraw, ImageFont


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
TEMPLATE_PATH = os.path.join(BASE_DIR, "template.jpg")


def _tmp_path(ext: str) -> str:
    ext = ext.lstrip(".")
    return os.path.join(tempfile.gettempdir(), f"ticket_{uuid.uuid4().hex[:12]}.{ext}")


def _load_font(filename: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = os.path.join(FONTS_DIR, filename)
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        # fallback, чтобы генерация не падала из-за шрифта
        return ImageFont.load_default()


FONT_TRANSPORT = _load_font("TTNormsPro-Medium.ttf", 54)
FONT_ROUTE = _load_font("TTNormsPro-Medium.ttf", 41)
FONT_REGULAR = _load_font("TTNormsPro-Normal.ttf", 48)


def generate_ticket(transport: str, number: str, route: str, garage_number: str) -> str:
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Не найден шаблон: {TEMPLATE_PATH}")

    img = Image.open(TEMPLATE_PATH).convert("RGB")
    draw = ImageDraw.Draw(img)

    # дата/время (Минск)
    minsk_time = datetime.now(pytz.timezone("Europe/Minsk"))
    date_text = minsk_time.strftime("%d.%m.%Y")
    time_text = minsk_time.strftime("%H:%M:%S")

    # заголовок "Автобус №12" по центру
    title = f"{transport} №{number}"
    tb = FONT_TRANSPORT.getbbox(title)
    tw = tb[2] - tb[0]
    draw.text((585 - tw / 2, 506), title, font=FONT_TRANSPORT, fill="black")

    # маршрут по центру
    rb = FONT_ROUTE.getbbox(route)
    rw = rb[2] - rb[0]
    draw.text((585 - rw / 2, 712), route, font=FONT_ROUTE, fill="black")

    # гаражный номер + подчёркивание (слева)
    gx, gy = 98, 950
    draw.text((gx, gy), garage_number, font=FONT_REGULAR, fill="black")
    gb = FONT_REGULAR.getbbox(garage_number)
    gw = gb[2] - gb[0]
    gh = gb[3] - gb[1]
    draw.line((gx, gy + gh + 20, gx + gw, gy + gh + 20), fill="black", width=2)

    # дата (слева)
    draw.text((98, 1072), date_text, font=FONT_REGULAR, fill="black")

    # время (справа, правый край = 1077)
    tb_time = FONT_REGULAR.getbbox(time_text)
    tw_time = tb_time[2] - tb_time[0]
    time_x_left = 1077 - tw_time
    draw.text((time_x_left, 1072), time_text, font=FONT_REGULAR, fill="black")

    # номер билета (правый край совпадает со временем, выше на 122px)
    rand_suffix = f"{random.randint(0, 999):03d}"
    ticket_no = f"ЭБ146775{rand_suffix}"
    ticket_y = 1072 - 122

    tb_ticket = FONT_REGULAR.getbbox(ticket_no)
    tw_ticket = tb_ticket[2] - tb_ticket[0]
    ticket_x_left = 1077 - tw_ticket

    draw.text((ticket_x_left, ticket_y), ticket_no, font=FONT_REGULAR, fill="black")

    # сохранение
    out_img = _tmp_path("jpg")
    img.save(out_img, format="JPEG", quality=95, optimize=True)
    return out_img
