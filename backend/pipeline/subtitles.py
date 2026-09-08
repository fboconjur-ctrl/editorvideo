"""Geração de arquivos .srt e queima (burn-in) de legendas no vídeo."""
import subprocess
from pathlib import Path

from .ffprobe_utils import probe_dimensions
from .transcribe import Segment

# Alinhamento no padrão ASS/libass: 2 = embaixo centralizado, 8 = em cima
# centralizado, 5 = centro da tela.
POSITION_TO_ALIGNMENT = {
    "bottom": 2,
    "top": 8,
    "middle": 5,
}


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


def burn_subtitles(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    font_size: int | None = None,
    position: str = "bottom",
) -> None:
    """Queima as legendas diretamente nos frames do vídeo via ffmpeg.

    `font_size=None` calcula um tamanho proporcional à altura do vídeo (em
    vez do tamanho fixo padrão do ffmpeg, que fica minúsculo em vídeos 4K
    e enorme em vídeos verticais pequenos).
    """
    _width, height = probe_dimensions(video_path)
    if font_size is None:
        font_size = max(12, round(height / 22))

    alignment = POSITION_TO_ALIGNMENT.get(position, 2)
    margin_v = round(height * 0.06)

    force_style = (
        f"FontSize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=2,Shadow=0,"
        f"Alignment={alignment},"
        f"MarginV={margin_v}"
    )

    srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{srt_escaped}':force_style='{force_style}'",
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
