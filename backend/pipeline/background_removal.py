"""Remoção de fundo de vídeo usando rembg (modelo open-source, roda 100%
local/offline após o primeiro download do modelo — sem chamadas pagas)."""
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from rembg import new_session, remove

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = new_session("u2net")
    return _session


def _probe_fps(video_path: Path) -> str:
    result = subprocess.run(
        [
            "ffprobe", "-v", "0",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "json",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    return data["streams"][0]["r_frame_rate"]


def remove_background(
    input_path: Path,
    output_path: Path,
    tmp_dir: Path,
    background_color: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """Remove o fundo do vídeo, frame a frame.

    - `background_color=None`: gera um `.webm` com canal alpha (fundo transparente).
    - `background_color="green"` (ou qualquer cor ffmpeg): compõe a pessoa
      sobre um fundo sólido dessa cor.
    - `progress_callback(frames_done, frames_total)`: chamado a cada frame
      processado. Sem isso a etapa fica minutos sem nenhum feedback (o
      modelo processa frame a frame na CPU), o que parece um travamento
      mesmo quando está funcionando normalmente.
    """
    frames_dir = tmp_dir / "frames"
    processed_dir = tmp_dir / "processed"
    frames_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    fps = _probe_fps(input_path)

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), str(frames_dir / "frame_%06d.png")],
        check=True, capture_output=True, text=True,
    )

    session = _get_session()
    frame_paths = sorted(frames_dir.glob("frame_*.png"))
    total = len(frame_paths)

    def _process_frame(frame_path: Path) -> None:
        result = remove(frame_path.read_bytes(), session=session)
        (processed_dir / frame_path.name).write_bytes(result)

    # A inferência do onnxruntime libera o GIL, então processar vários
    # frames em paralelo com threads dá um ganho real de velocidade (não é
    # só um paralelismo aparente), sem precisar reescrever pra
    # multiprocessing nem duplicar o modelo carregado na memória.
    max_workers = min(4, os.cpu_count() or 1)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for _ in executor.map(_process_frame, frame_paths):
            done += 1
            if progress_callback:
                progress_callback(done, total)

    if background_color:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", fps, "-i", str(processed_dir / "frame_%06d.png"),
            "-i", str(input_path),
            "-f", "lavfi", "-i", f"color=c={background_color}",
            "-filter_complex",
            "[2:v][0:v]scale2ref[bg][fg];[bg][fg]overlay=shortest=1:format=auto[outv]",
            "-map", "[outv]", "-map", "1:a?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", fps, "-i", str(processed_dir / "frame_%06d.png"),
            "-i", str(input_path),
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
            str(output_path),
        ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)
    shutil.rmtree(tmp_dir, ignore_errors=True)
