# video_overlay.py
import os
import uuid
import tempfile
import numpy as np
from PIL import Image
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip

def _tmp_path(ext: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"vid_{uuid.uuid4().hex[:12]}.{ext.lstrip('.')}")

def make_video_with_overlay(
    base_video_path: str,
    overlay_image_path: str,
    output_path: str = None,
    crop_top_px: int = 200,
    keep_ratio: bool = False,   # у тебя размеры совпадают — оставляем False
):
    # Проверки путей
    if not os.path.exists(base_video_path):
        raise FileNotFoundError(f"[make_video] Нет базового видео: {base_video_path}")
    if not os.path.exists(overlay_image_path):
        raise FileNotFoundError(f"[make_video] Нет оверлея: {overlay_image_path}")

    base = VideoFileClip(base_video_path)
    W, H = base.w, base.h
    print(f"[make_video] base {base_video_path} {W}x{H} dur={base.duration}s fps={getattr(base,'fps',None)}", flush=True)

    img = Image.open(overlay_image_path).convert("RGBA")
    iw, ih = img.size
    print(f"[make_video] overlay {overlay_image_path} {iw}x{ih}", flush=True)

    # Подгон размеров, если вдруг не совпадают
    if (iw, ih) != (W, H):
        if keep_ratio:
            new_w = W
            new_h = int(ih * (W / iw))
            img = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            img = img.resize((W, H), Image.LANCZOS)
        iw, ih = img.size
        print(f"[make_video] overlay resized to {iw}x{ih}", flush=True)

    crop = max(0, min(crop_top_px, ih - 1))
    img_cropped = img.crop((0, crop, iw, ih))  # (left, top, right, bottom)

    overlay = ImageClip(np.array(img_cropped)).set_duration(base.duration)
    overlay = overlay.set_position((0, crop))  # x=0, y=crop

    composite = CompositeVideoClip([base, overlay], size=(W, H))

    if output_path is None:
        output_path = _tmp_path("mp4")

    print(f"[make_video] writing {output_path}", flush=True)
    composite.write_videofile(
        output_path,
        codec="libx264",
        fps=getattr(base, "fps", 25) or 25,
        audio=False,
        preset="veryfast",
        threads=2,
        logger=None,
    )
    composite.close()
    base.close()

    # финальная проверка
    sz = os.path.getsize(output_path)
    print(f"[make_video] done {output_path} size={sz} bytes", flush=True)
    if sz == 0:
        raise RuntimeError("Сгенерирован пустой mp4 (size=0)")
    return output_path
