"""Texto para voz (TTS) local, usando pyttsx3 — no Windows usa as vozes
SAPI5 já instaladas no sistema, sem precisar baixar modelo nem internet."""
from pathlib import Path

import pyttsx3


def synthesize_speech(text: str, output_path: Path, rate: int | None = None) -> None:
    engine = pyttsx3.init()
    if rate:
        engine.setProperty("rate", rate)
    engine.save_to_file(text, str(output_path))
    engine.runAndWait()
