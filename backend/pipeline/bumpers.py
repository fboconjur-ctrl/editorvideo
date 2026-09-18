"""Armazenamento dos vídeos próprios reaproveitáveis no texto-para-vídeo
— abertura, encerramento e a camada de webcam/reação — que o usuário sobe
uma vez e usa em toda geração depois, sem precisar subir de novo."""
import shutil
from pathlib import Path

_BUMPERS_DIR = Path(__file__).parent.parent / "user_media"


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
