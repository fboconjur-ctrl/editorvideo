"""Upscale de resolução via ffmpeg (reamostragem Lanczos + nitidez).

Importante: isto NÃO é super-resolução por IA (tipo Real-ESRGAN) — é troca
de resolução com um filtro de reamostragem de alta qualidade mais um
realce de nitidez. Deixa o vídeo maior e mais nítido, mas não "inventa"
detalhe como um modelo generativo faria. Ainda assim é gratuito, local e
instantâneo (não depende de GPU nem de baixar modelos grandes).
"""
import subprocess
from pathlib import Path


def upscale(input_path: Path, output_path: Path, scale_factor: float = 2.0) -> None:
    vf = f"scale=iw*{scale_factor}:ih*{scale_factor}:flags=lanczos,unsharp=5:5:0.8:3:3:0.4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
