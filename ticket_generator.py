# ticket_generator.py
import os, uuid, tempfile
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import pytz
from video_overlay import make_video_with_overlay


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _tmp_path(ext: str) -> str:
    """Уникальный файл во /tmp, чтобы не было конфликтов при нескольких пользователях."""
    return os.path.join(tempfile.gettempdir(), f"ticket_{uuid.uuid4().hex[:12]}.{ext.lstrip('.')}")

def generate_ticket(transport, number, route, garage_number):
    img = Image.open(os.path.join(BASE_DIR, "template.jpg")).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Шрифты
    font_transport = ImageFont.truetype(os.path.join(BASE_DIR, "fonts", "TTNormsPro-Medium.ttf"), size=54)
    font_route     = ImageFont.truetype(os.path.join(BASE_DIR, "fonts", "TTNormsPro-Medium.ttf"), size=41)
    font_regular   = ImageFont.truetype(os.path.join(BASE_DIR, "fonts", "TTNormsPro-Normal.ttf"), size=48)

    # Время и дата (Минск)
    minsk_time = datetime.now(pytz.timezone("Europe/Minsk"))
    date_text = minsk_time.strftime("%d.%m.%Y")
    time_text = minsk_time.strftime("%H:%M:%S")

    # ==== Заголовок (центр по x = 585, y = 506) ====
    text = f"{transport} №{number}"
    bbox = font_transport.getbbox(text)
    text_width = bbox[2] - bbox[0]
    draw.text((585 - text_width / 2, 506), text, font=font_transport, fill="black")

    # ==== Маршрут (центр по x = 585, y = 712) ====
    text = route
    bbox = font_route.getbbox(text)
    text_width = bbox[2] - bbox[0]
    draw.text((585 - text_width / 2, 712), text, font=font_route, fill="black")

    # ==== Гаражный номер с подчёркиванием ====
    garage_x = 98
    garage_y = 950
    draw.text((garage_x, garage_y), garage_number, font=font_regular, fill="black")

    bbox = font_regular.getbbox(garage_number)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    underline_y = garage_y + text_height + 20
    draw.line((garage_x, underline_y, garage_x + text_width, underline_y), fill="black", width=2)

    # ==== Дата (лево) ====
    draw.text((98, 1072), date_text, font=font_regular, fill="black")

    # ==== Время (право) ====
    bbox = font_regular.getbbox(time_text)
    text_width = bbox[2] - bbox[0]
    draw.text((1077 - text_width, 1072), time_text, font=font_regular, fill="black")

    # сохраняем в уникальный путь и ВОЗВРАЩАЕМ его
    out_img = _tmp_path("jpg")
    img.save(out_img, quality=95, optimize=True)
    return out_img

def generate_ticket_video(transport, number, route, garage_number, base_video="anim.mp4", crop_top_px=200):
    img_path = generate_ticket(transport, number, route, garage_number)

    base_video_path = os.path.join(BASE_DIR, base_video)  # anim.mp4 лежит в корне рядом с кодом
    if not os.path.exists(base_video_path):
        raise FileNotFoundError(f"Не найден файл анимации {base_video_path}. Положи anim.mp4 рядом с кодом.")

    out_video = make_video_with_overlay(
        base_video_path=base_video_path,
        overlay_image_path=img_path,
        output_path=None,       # /tmp + уникальное имя
        crop_top_px=crop_top_px,
        keep_ratio=False
    )
    return img_path, out_video
