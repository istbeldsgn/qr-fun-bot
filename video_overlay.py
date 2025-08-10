# video_overlay.py
import os, uuid, tempfile, shutil, subprocess

def _tmp(ext: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"vid_{uuid.uuid4().hex[:10]}.{ext.lstrip('.')}")

def ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None

def make_video_with_overlay(
    base_video_path: str,
    overlay_image_path: str,
    output_path: str | None = None,
    crop_top_px: int = 200,
) -> str:
    """
    Накладывает ОБРЕЗАННУЮ сверху (на crop_top_px) картинку на видео ровно по размеру (размеры совпадают),
    верхние 200px видео остаются видимыми. Требуется ffmpeg в PATH.
    """
    if not ffmpeg_ok():
        raise FileNotFoundError("ffmpeg не найден в системе")

    if not os.path.exists(base_video_path):
        raise FileNotFoundError(f"Нет базового видео: {base_video_path}")
    if not os.path.exists(overlay_image_path):
        raise FileNotFoundError(f"Нет оверлея: {overlay_image_path}")

    out = output_path or _tmp("mp4")

    # [1:v] — картинка, обрежем верх на crop_top_px. Затем наложим её на [0:v] на смещении y=crop_top_px.
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
        "-crf", "24",
        "-pix_fmt", "yuv420p",
        "-an",
        out,
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError("ffmpeg отдал пустой файл")
    return out
