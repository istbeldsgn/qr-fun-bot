# video_overlay.py
import os, uuid, tempfile, subprocess

def _tmp(ext): 
    return os.path.join(tempfile.gettempdir(), f"vid_{uuid.uuid4().hex[:10]}.{ext}")

def make_video_with_overlay(
    base_video_path: str,
    overlay_image_path: str,
    output_path: str | None = None,
    crop_top_px: int = 200,
    keep_ratio: bool = False,   # у вас макеты совпадают с размером видео — можно оставить False
):
    if not os.path.exists(base_video_path):
        raise FileNotFoundError(f"Нет базового видео: {base_video_path}")
    if not os.path.exists(overlay_image_path):
        raise FileNotFoundError(f"Нет оверлея: {overlay_image_path}")

    out = output_path or _tmp("mp4")

    # Обрезаем у оверлея верх на crop_top_px и накладываем оверлей на позицию y=crop_top_px
    # Требование: размер overlay_image == размеру видео.
    filter_complex = (
        f"[1:v]crop=iw:ih-{crop_top_px}:0:{crop_top_px}[ov];"
        f"[0:v][ov]overlay=0:{crop_top_px}:format=auto"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", base_video_path,
        "-i", overlay_image_path,
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "24",                # можно поднять до 26–28, чтобы ещё снизить нагрузку
        "-pix_fmt", "yuv420p",
        "-an",
        out,
    ]

    # глушим вывод, чтобы не забивать память логами
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    if os.path.getsize(out) == 0:
        raise RuntimeError("Пустой mp4 (size=0)")
    return out
