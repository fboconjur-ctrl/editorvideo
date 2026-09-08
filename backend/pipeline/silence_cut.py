"""Corte automático de silêncios/pausas usando auto-editor."""
import subprocess
from pathlib import Path


def cut_silence(input_path: Path, output_path: Path, margin: str = "0.15sec") -> None:
    """Remove silêncios do vídeo mantendo margens pequenas ao redor da fala.

    auto-editor decide os cortes olhando o volume do áudio; não altera cor,
    velocidade ou conteúdo, só remove trechos sem fala.
    """
    cmd = [
        "auto-editor",
        str(input_path),
        "--margin", margin,
        "--output", str(output_path),
        "--no-open",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
