"""Armazenamento dos vídeos próprios reaproveitáveis no texto-para-vídeo
— abertura, encerramento e a camada de webcam/reação — que o usuário sobe
uma vez e usa em toda geração depois, sem precisar subir de novo."""
import random
import shutil
from pathlib import Path

_BUMPERS_DIR = Path(__file__).parent.parent / "user_media"
_WEBCAM_SUBDIR = _BUMPERS_DIR / "webcam_clips"


def _ensure_dir() -> None:
    _BUMPERS_DIR.mkdir(parents=True, exist_ok=True)


def save_bumper(which: str, filename: str, file_obj) -> Path:
    """`which`: "intro" ou "outro". Remove qualquer arquivo anterior salvo
    pra esse tipo antes de salvar o novo (não acumula lixo com extensões
    diferentes de uploads anteriores)."""
    _ensure_dir()
    remove_bumper(which)
    suffix = Path(filename).suffix or ".mp4"
    path = _BUMPERS_DIR / f"{which}{suffix}"
    with path.open("wb") as f:
        shutil.copyfileobj(file_obj, f)
    return path


def get_bumper_path(which: str) -> Path | None:
    if not _BUMPERS_DIR.exists():
        return None
    matches = list(_BUMPERS_DIR.glob(f"{which}.*"))
    return matches[0] if matches else None


def remove_bumper(which: str) -> None:
    if not _BUMPERS_DIR.exists():
        return
    for match in _BUMPERS_DIR.glob(f"{which}.*"):
        match.unlink(missing_ok=True)


# --- Camada de webcam/reação: um POOL de clipes, não um único arquivo ---
# Grava vários vídeos de reação diferentes (poses/momentos distintos) e o
# app sorteia um a cada vídeo gerado, em vez de repetir sempre o mesmo
# clipe curto em loop (o que ficava com "saltos" visuais perceptíveis).


def add_webcam_clip(filename: str, file_obj) -> Path:
    _WEBCAM_SUBDIR.mkdir(parents=True, exist_ok=True)
    existing = list_webcam_clips()
    indices = [int(p.stem.split("_")[-1]) for p in existing if p.stem.rsplit("_", 1)[-1].isdigit()]
    next_index = max(indices, default=-1) + 1
    suffix = Path(filename).suffix or ".mp4"
    path = _WEBCAM_SUBDIR / f"clip_{next_index}{suffix}"
    with path.open("wb") as f:
        shutil.copyfileobj(file_obj, f)
    return path


def list_webcam_clips() -> list[Path]:
    if not _WEBCAM_SUBDIR.exists():
        return []
    return sorted(_WEBCAM_SUBDIR.iterdir())


def remove_webcam_clip(clip_name: str) -> None:
    """`clip_name` vem direto de uma URL da API — nunca confiar nele sem
    checar que o caminho final continua dentro de `_WEBCAM_SUBDIR` (evita
    apagar arquivo fora da pasta via algo tipo "../../main.py")."""
    if not _WEBCAM_SUBDIR.exists():
        return
    path = (_WEBCAM_SUBDIR / clip_name).resolve()
    if path.is_relative_to(_WEBCAM_SUBDIR.resolve()) and path.exists():
        path.unlink()


def get_random_webcam_clip() -> Path | None:
    clips = list_webcam_clips()
    return random.choice(clips) if clips else None
