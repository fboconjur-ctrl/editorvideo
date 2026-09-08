"""Reframe automático para vertical (9:16), seguindo o rosto/pessoa em cena.

Usa MediaPipe (modelo leve, roda local em CPU) para detectar rostos em uma
amostra de frames, calcula o centro médio horizontal e recorta um "crop"
vertical fixo centralizado nesse ponto. É um recorte estático (não segue
movimento frame a frame) — suficiente pra maioria dos vídeos de talking-head,
e muito mais barato do que rastreamento por frame.
"""
import json
import subprocess
from pathlib import Path

import cv2


def _get_face_detection_module():
    """Import "preguiçoso" do submódulo de detecção de rosto.

    Feito sob demanda (em vez de no topo do arquivo) para que uma falha de
    import do mediapipe quebre só o recurso de reframe, não o servidor
    inteiro na inicialização. Em versões recentes do mediapipe o atalho
    `mediapipe.solutions` nem sempre fica disponível via
    `import mediapipe as mp; mp.solutions...`, então importamos o
    submódulo diretamente.
    """
    try:
        from mediapipe.python.solutions import face_detection as mp_face_detection
        return mp_face_detection
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Não foi possível carregar o detector de rosto do mediapipe "
            "(a versão instalada pode ter mudado a API). Tente "
            "`pip install -U mediapipe` no ambiente virtual do backend."
        ) from exc

TARGET_ASPECT = 9 / 16


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
    cap = cv2.VideoCapture(str(video_path))
    centers: list[float] = []

    mp_face_detection = _get_face_detection_module()
    with mp_face_detection.FaceDetection(min_detection_confidence=0.5) as detector:
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % sample_every_n_frames == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.process(rgb_frame)
                if result.detections:
                    for detection in result.detections:
                        box = detection.location_data.relative_bounding_box
                        centers.append(box.xmin + box.width / 2)
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
