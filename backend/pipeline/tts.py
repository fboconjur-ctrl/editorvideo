"""Texto para voz (TTS) local, usando pyttsx3 — no Windows usa as vozes
SAPI5 já instaladas no sistema, sem precisar baixar modelo nem internet."""
from dataclasses import dataclass
from pathlib import Path

import pyttsx3


@dataclass
class VoiceInfo:
    id: str
    name: str
    languages: list[str]


def list_voices() -> list[VoiceInfo]:
    engine = pyttsx3.init()
    voices = engine.getProperty("voices") or []
    result = []
    for voice in voices:
        langs = voice.languages or []
        decoded = [l.decode("utf-8", "ignore") if isinstance(l, bytes) else str(l) for l in langs]
        result.append(VoiceInfo(id=voice.id, name=voice.name, languages=decoded))
    return result


def synthesize_speech(
    text: str, output_path: Path, rate: int | None = None, voice_id: str | None = None
) -> None:
    engine = pyttsx3.init()
    if rate:
        engine.setProperty("rate", rate)
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.save_to_file(text, str(output_path))
    engine.runAndWait()
