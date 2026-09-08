"""Transcrição local de áudio usando faster-whisper (sem chamadas externas)."""
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

_MODEL_SIZE = "small"  # troque para "base" (mais rápido) ou "medium" (mais preciso)
_model: WhisperModel | None = None


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Word:
    start: float
    end: float
    text: str


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        # compute_type="int8" roda bem em CPU; troque para "float16" se tiver GPU CUDA
        _model = WhisperModel(_MODEL_SIZE, device="auto", compute_type="int8")
    return _model


def transcribe(video_path: Path, language: str | None = "pt") -> list[Segment]:
    model = _get_model()
    segments, _info = model.transcribe(str(video_path), language=language, vad_filter=True)
    return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in segments]


def transcribe_words(video_path: Path, language: str | None = "pt") -> list[Word]:
    """Transcrição com timestamp por palavra — usada para localizar palavras
    repetidas e vícios de fala ("filler words") a serem cortados."""
    model = _get_model()
    segments, _info = model.transcribe(
        str(video_path), language=language, vad_filter=True, word_timestamps=True
    )
    words: list[Word] = []
    for segment in segments:
        for word in segment.words or []:
            words.append(Word(start=word.start, end=word.end, text=word.word.strip()))
    return words
