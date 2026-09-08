"""Estabilização de vídeo tremido usando o filtro vidstab do ffmpeg
(processo em duas passadas, tudo local)."""
import subprocess
import tempfile
from pathlib import Path


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if "vidstab" in stderr.lower() or "no such filter" in stderr.lower() or "unknown filter" in stderr.lower():
            raise RuntimeError(
                "Seu ffmpeg não tem suporte ao filtro vidstab (necessário para "
                "estabilizar vídeo). Baixe um build 'full' do ffmpeg (ex: em "
                "https://www.gyan.dev/ffmpeg/builds/ escolha a versão 'full', não "
                "'essentials') e substitua o ffmpeg no seu PATH, ou desmarque a "
                "opção 'Estabilizar imagem tremida'."
            ) from exc
        raise RuntimeError(f"Falha ao estabilizar o vídeo: {stderr[-800:]}") from exc


def stabilize(input_path: Path, output_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        transforms_file = Path(tmp) / "transforms.trf"

        _run([
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"vidstabdetect=shakiness=5:accuracy=15:result={transforms_file}",
            "-f", "null", "-",
        ])

        _run([
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"vidstabtransform=input={transforms_file}:zoom=0:smoothing=15,unsharp=5:5:0.8:3:3:0.4",
            "-c:a", "copy",
            str(output_path),
        ])
