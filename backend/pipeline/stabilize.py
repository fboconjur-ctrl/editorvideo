"""Estabilização de vídeo tremido usando o filtro vidstab do ffmpeg
(processo em duas passadas, tudo local)."""
import subprocess
import tempfile
from pathlib import Path


def stabilize(input_path: Path, output_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        transforms_file = Path(tmp) / "transforms.trf"

        detect_cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"vidstabdetect=shakiness=5:accuracy=15:result={transforms_file}",
            "-f", "null", "-",
        ]
        subprocess.run(detect_cmd, check=True, capture_output=True, text=True)

        transform_cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"vidstabtransform=input={transforms_file}:zoom=0:smoothing=15,unsharp=5:5:0.8:3:3:0.4",
            "-c:a", "copy",
            str(output_path),
        ]
        subprocess.run(transform_cmd, check=True, capture_output=True, text=True)
