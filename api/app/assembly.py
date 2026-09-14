"""Сборка ролика через ffmpeg (Фаза 5).

Каждый шот → клип: визуал (видео DoP, либо кадр как статичный план) + сведённый звук
(голос + музыка + SFX через amix). Затем клипы конкатенируются в финал.

ffmpeg локально может отсутствовать — на VPS он есть в Docker-образе api.
Команды строятся чистыми функциями (тестируемо без ffmpeg).
"""
import os
import shutil
import subprocess
import uuid

from .config import settings


class FFmpegMissing(RuntimeError):
    pass


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FFmpegMissing("ffmpeg не найден (в Docker-образе api он установлен)")
    return exe


def fs_path(url: str) -> str:
    """/media/<name> → путь файла на диске."""
    return os.path.join(settings.media_dir, url.rsplit("/", 1)[-1])


def shot_clip_cmd(*, video: str | None, frame: str | None,
                  audios: list[str], duration: float, out: str) -> list[str]:
    """Строит ffmpeg-команду одного шота. Порядок опций валиден для ffmpeg."""
    args: list[str] = ["ffmpeg", "-y"]
    # видеовход
    if video:
        args += ["-i", video]
    elif frame:
        args += ["-loop", "1", "-t", f"{duration}", "-i", frame]
    else:
        args += ["-f", "lavfi", "-t", f"{duration}", "-i", "color=c=black:s=1280x720:r=30"]
    # аудиовходы
    for a in audios:
        args += ["-i", a]

    n = len(audios)
    filter_complex = None
    amap = None
    if n == 1:
        amap = "1:a"
    elif n > 1:
        labels = "".join(f"[{i + 1}:a]" for i in range(n))
        filter_complex = f"{labels}amix=inputs={n}:duration=longest:normalize=0[aout]"
        amap = "[aout]"

    if filter_complex:
        args += ["-filter_complex", filter_complex]
    args += ["-map", "0:v"]
    if amap:
        args += ["-map", amap]
    args += ["-t", f"{duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30"]
    if amap:
        args += ["-c:a", "aac", "-shortest"]
    args += [out]
    return args


def concat_cmd(list_file: str, out: str) -> list[str]:
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", out]


def _run(args: list[str]) -> None:
    args = [_ffmpeg()] + args[1:]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")


def assemble(shots: list[dict], out_name: str = "final") -> str:
    """shots: список {video_url, frame_url, audio_urls, duration}. Возвращает /media/<final>.mp4."""
    os.makedirs(settings.media_dir, exist_ok=True)
    work = os.path.join(settings.media_dir, f".work_{uuid.uuid4().hex}")
    os.makedirs(work, exist_ok=True)
    clip_paths: list[str] = []
    for i, s in enumerate(shots):
        clip = os.path.join(work, f"clip_{i:03d}.mp4")
        cmd = shot_clip_cmd(
            video=fs_path(s["video_url"]) if s.get("video_url") else None,
            frame=fs_path(s["frame_url"]) if s.get("frame_url") else None,
            audios=[fs_path(u) for u in s.get("audio_urls", []) if u],
            duration=s.get("duration", 5),
            out=clip,
        )
        _run(cmd)
        clip_paths.append(clip)

    list_file = os.path.join(work, "list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clip_paths:
            f.write(f"file '{c.replace(os.sep, '/')}'\n")

    final_name = f"{out_name}_{uuid.uuid4().hex}.mp4"
    final_path = os.path.join(settings.media_dir, final_name)
    _run(concat_cmd(list_file, final_path))
    shutil.rmtree(work, ignore_errors=True)
    return f"/media/{final_name}"
