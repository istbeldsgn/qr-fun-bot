# video_overlay.py
from PIL import Image
import numpy as np
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip

def make_video_with_overlay(
    base_video_path: str,
    overlay_image_path: str,
    output_path: str = "out.mp4",
    crop_top_px: int = 200,
    keep_ratio: bool = True,
    codec: str = "libx264",
    preset: str = "veryfast",
    audio: bool = False,
):
    """
    Кладёт поверх видео статичное изображение, предварительно отрезав сверху crop_top_px.
    Смещение по Y = crop_top_px, чтобы визуально картинка осталась «на своём месте».
    """
    # 1) База — видео/анимация
    base = VideoFileClip(base_video_path)  # gif/mp4 — ок
    W, H = base.w, base.h

    # 2) Готовим оверлей (фото)
    img = Image.open(overlay_image_path).convert("RGBA")
    iw, ih = img.size

    # Если размеры совпадают — отлично. Если нет — приводим по ширине/высоте видео.
    if (iw, ih) != (W, H):
        if keep_ratio:
            # подгоняем по ширине видео, по высоте — пропорционально (чтобы не тянуть лица)
            new_w = W
            new_h = int(ih * (W / iw))
            img = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            img = img.resize((W, H), Image.LANCZOS)

        iw, ih = img.size

    # 3) Режем верх
    crop = max(0, min(crop_top_px, ih - 1))
    img_cropped = img.crop((0, crop, iw, ih))  # (left, top, right, bottom)

    # 4) Кладём поверх: смещение по Y = crop, чтобы «оставшаяся» часть легла туда же
    overlay = ImageClip(np.array(img_cropped)).set_duration(base.duration)
    overlay = overlay.set_position((0, crop))  # x=0, y=crop

    composite = CompositeVideoClip([base, overlay], size=(W, H))

    # 5) Сохраняем mp4
    # fps берём у базы; звук по умолчанию отключен (audio=False)
    composite.write_videofile(
        output_path,
        codec=codec,
        fps=getattr(base, "fps", 25),
        audio=audio,
        preset=preset,
        threads=2,  # можно 2–4
        logger=None,
    )

    base.close()
    composite.close()
    return output_path
