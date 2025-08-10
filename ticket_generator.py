# ticket_generator.py
import os
import uuid
import tempfile
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import pytz
from video_overlay import make_video_with_overlay, ffmpeg_ok  # ← добавили

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

def _tmp_path(ext: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"ticket_{uuid.uuid4().hex[:12]}.{ext.lstrip('.')}")

def _load_font(filename: str, size: int):
    path = os.path.join(FONTS_DIR, filename)
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()

FONT_TRANSPORT = _load_font("TTNormsPro-Medium.ttf", 54)
FONT_ROUTE     = _load_font("TTNormsPro-Medium.ttf", 41)
FONT_REGULAR   = _load_font("TTNormsPro-Normal.ttf", 48)

def generate_ticket(transport: str, number: str, route: str, garage_number: str) -> str:
    template_path = os.path.join(BASE_DIR, "template.jpg")
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Не найден шаблон: {template_path}")

    img = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    minsk_time = datetime.now(pytz.timezone("Europe/Minsk"))
    date_text = minsk_time.strftime("%d.%m.%Y")
    time_text = minsk_time.strftime("%H:%M:%S")

    title = f"{transport} №{number}"
    tb = FONT_TRANSPORT.getbbox(title); tw = tb[2] - tb[0]
    draw.text((585 - tw / 2, 506), title, font=FONT_TRANSPORT, fill="black")

    rb = FONT_ROUTE.getbbox(route); rw = rb[2] - rb[0]
    draw.text((585 - rw / 2, 712), route, font=FONT_ROUTE, fill="black")

    gx, gy = 98, 950
    draw.text((gx, gy), garage_number, font=FONT_REGULAR, fill="black")
    gb = FONT_REGULAR.getbbox(garage_number); gw = gb[2] - gb[0]; gh = gb[3] - gb[1]
    draw.line((gx, gy + gh + 20, gx + gw, gy + gh + 20), fill="black", width=2)

    draw.text((98, 1072), date_text, font=FONT_REGULAR, fill="black")
    tb = FONT_REGULAR.getbbox(time_text); tw = tb[2] - tb[0]
    draw.text((1077 - tw, 1072), time_text, font=FONT_REGULAR, fill="black")

    out_img = _tmp_path("jpg")
    img.save(out_img, format="JPEG", quality=95, optimize=True)
    return out_img

def generate_ticket_video(
    transport: str,
    number: str,
    route: str,
    garage_number: str,
    base_video: str = "anim.mp4",
    crop_top_px: int = 200,
):
    """
    Возвращает (img_path, video_path). Если ffmpeg/видео отсутствуют — кидает исключение.
    """
    img_path = generate_ticket(transport, number, route, garage_number)

    if not ffmpeg_ok():
        raise FileNotFoundError("ffmpeg отсутствует")

    base_video_path = os.path.join(BASE_DIR, base_video)
    video_path = make_video_with_overlay(
        base_video_path=base_video_path,
        overlay_image_path=img_path,
        output_path=None,
        crop_top_px=crop_top_px,
    )
    return img_path, video_path
