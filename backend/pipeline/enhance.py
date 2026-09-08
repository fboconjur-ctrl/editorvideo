"""Correção automática de cor e normalização de áudio, tudo via filtros
nativos do ffmpeg (sem modelo de IA nenhum)."""
import subprocess
from pathlib import Path


def enhance(input_path: Path, output_path: Path) -> None:
    """Aplica em uma única passada:

    - `normalize`: ajusta automaticamente níveis de preto/branco e balanço
      de cor por frame (equivalente ao "auto color" do CapCut).
    - `eq`: leve ganho de contraste/saturação para compensar vídeos "lavados".
    - `loudnorm`: normalização de volume ao padrão EBU R128 (-16 LUFS),
      corrige trechos muito altos/baixos de forma consistente.
    """
    video_filter = "normalize,eq=contrast=1.05:saturation=1.08"
    audio_filter = "loudnorm=I=-16:TP=-1.5:LRA=11"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", video_filter,
        "-af", audio_filter,
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
