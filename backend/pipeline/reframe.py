"""Reframe automático para vertical (9:16), seguindo o rosto/pessoa em cena.

Usa o detector de rosto Haar Cascade embutido no OpenCV (leve, roda local
em CPU, sem baixar modelo) para detectar rostos numa amostra de frames,
calcula o centro médio horizontal e recorta um "crop" vertical fixo
centralizado nesse ponto. É um recorte estático (não segue movimento
frame a frame) — suficiente pra maioria dos vídeos de talking-head, e
muito mais barato do que rastreamento por frame.

O arquivo do detector (haarcascade_frontalface_default.xml) vem
empacotado direto no projeto em vez de depender do pacote opencv-python
trazê-lo — versões diferentes do pacote nem sempre incluem esse arquivo,
e usar uma cópia própria evita esse tipo de instabilidade entre ambientes.
"""
import json
import subprocess
from pathlib import Path

import cv2

TARGET_ASPECT = 9 / 16
_CASCADE_PATH = Path(__file__).parent / "data" / "haarcascade_frontalface_default.xml"

_face_cascade: cv2.CascadeClassifier | None = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    global _face_cascade
    if _face_cascade is None:
        cascade = cv2.CascadeClassifier(str(_CASCADE_PATH))
        if cascade.empty():
            raise RuntimeError(
                f"Não foi possível carregar o detector de rosto em {_CASCADE_PATH}. "
                "Verifique se o arquivo não foi corrompido/removido do repositório."
            )
        _face_cascade = cascade
    return _face_cascade


def _probe_dimensions(video_path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "0",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    return stream["width"], stream["height"]


def _average_face_center_x(video_path: Path, sample_every_n_frames: int = 15) -> float | None:
    """Retorna o centro horizontal médio dos rostos detectados, normalizado
    entre 0 e 1. Retorna None se nenhum rosto for encontrado (nesse caso o
    chamador deve usar o centro geométrico do vídeo)."""
    cascade = _get_face_cascade()
    cap = cv2.VideoCapture(str(video_path))
    centers: list[float] = []

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_index % sample_every_n_frames == 0:
            frame_width = frame.shape[1]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
            for x, y, w, h in faces:
                centers.append((x + w / 2) / frame_width)
        frame_index += 1

    cap.release()
    if not centers:
        return None
    return sum(centers) / len(centers)


def reframe_vertical(input_path: Path, output_path: Path) -> None:
    width, height = _probe_dimensions(input_path)

    center_x_norm = _average_face_center_x(input_path)
    if center_x_norm is None:
        center_x_norm = 0.5

    crop_width = round(height * TARGET_ASPECT)
    crop_width = min(crop_width, width)

    center_x_px = center_x_norm * width
    crop_x = round(center_x_px - crop_width / 2)
    crop_x = max(0, min(crop_x, width - crop_width))

    vf = f"crop={crop_width}:{height}:{crop_x}:0,scale=1080:1920"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
