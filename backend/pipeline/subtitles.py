"""Geração de arquivos .srt e queima (burn-in) de legendas no vídeo."""
import subprocess
from pathlib import Path

from .transcribe import Segment


def _format_timestamp(seconds: float) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    millis = int((secs - int(secs)) * 1000)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d},{millis:03d}"


def write_srt(segments: list[Segment], srt_path: Path) -> None:
    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}")
        lines.append(seg.text)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> None:
    """Queima as legendas diretamente nos frames do vídeo via ffmpeg."""
    srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{srt_escaped}'",
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
