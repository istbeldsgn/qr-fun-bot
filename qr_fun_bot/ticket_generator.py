from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import pytz

def generate_ticket(transport, number, route, garage_number):
    img = Image.open("template.jpg").convert("RGB")
    draw = ImageDraw.Draw(img)

    # Шрифты
    font_transport = ImageFont.truetype("fonts/TTNormsPro-Medium.ttf", size=54)
    font_route = ImageFont.truetype("fonts/TTNormsPro-Medium.ttf", size=41)
    font_regular = ImageFont.truetype("fonts/TTNormsPro-Normal.ttf", size=48)

    # Время и дата (Минск)
    minsk_time = datetime.now(pytz.timezone("Europe/Minsk"))
    date_text = minsk_time.strftime("%d.%m.%Y")
    time_text = minsk_time.strftime("%H:%M:%S")

    # ==== Автобус №12 — центрирование по x = 412, y = 506 ====
    text = f"{transport} №{number}"
    bbox = font_transport.getbbox(text)
    text_width = bbox[2] - bbox[0]
    draw.text((585 - text_width / 2, 506), text, font=font_transport, fill="black")

    # ==== Маршрут — центрирование по x = 330, y = 712 ====
    text = route
    bbox = font_route.getbbox(text)
    text_width = bbox[2] - bbox[0]
    draw.text((585 - text_width / 2, 712), text, font=font_route, fill="black")

   
     # ==== Гаражный номер с подчёркиванием вручную ====
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

    # ==== Время (право), x = 940 ====
    bbox = font_regular.getbbox(time_text)
    text_width = bbox[2] - bbox[0]
    draw.text((1077 - text_width, 1072), time_text, font=font_regular, fill="black")

    img.save("result.jpg", quality=95, optimize=True)
    return "result.jpg"
