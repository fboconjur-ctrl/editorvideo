"""Texto para voz (TTS) — dois motores:

- `pyttsx3` (local/offline): usa as vozes já instaladas no sistema
  operacional (SAPI5 no Windows), sem internet.
- `edge-tts` (online, mas gratuito e sem chave de API): usa as vozes
  neurais da Microsoft (as mesmas do Edge/Narrador moderno), muito mais
  naturais, mas precisam de internet.
"""
import asyncio
from dataclasses import dataclass
from pathlib import Path

import edge_tts
import pyttsx3


@dataclass
class VoiceInfo:
    id: str
    name: str
    languages: list[str]


def list_local_voices() -> list[VoiceInfo]:
    engine = pyttsx3.init()
    voices = engine.getProperty("voices") or []
    result = []
    for voice in voices:
        langs = voice.languages or []
        decoded = [l.decode("utf-8", "ignore") if isinstance(l, bytes) else str(l) for l in langs]
        result.append(VoiceInfo(id=voice.id, name=voice.name, languages=decoded))
    return result


def synthesize_speech_local(
    text: str, output_path: Path, rate: int | None = None, voice_id: str | None = None
) -> None:
    engine = pyttsx3.init()
    if rate:
        engine.setProperty("rate", rate)
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.save_to_file(text, str(output_path))
    engine.runAndWait()


# Lista curada das vozes neurais mais úteis (pt-BR, pt-PT, en-US) — a lista
# completa do edge-tts tem centenas de vozes; filtramos pra não sobrecarregar
# o seletor da interface.
_EDGE_LANG_PREFIXES = ("pt-BR", "pt-PT", "en-US", "en-GB", "es-ES", "es-MX")


def list_edge_voices() -> list[VoiceInfo]:
    async def _fetch():
        return await edge_tts.list_voices()

    all_voices = asyncio.run(_fetch())
    result = []
    for v in all_voices:
        if v["Locale"].startswith(_EDGE_LANG_PREFIXES):
            result.append(VoiceInfo(id=v["ShortName"], name=f"{v['FriendlyName']}", languages=[v["Locale"]]))
    return result


def synthesize_speech_edge(text: str, output_path: Path, voice_id: str | None = None, rate: int | None = None) -> None:
    """`rate` aqui é um ajuste percentual de velocidade (ex: 20 = 20% mais
    rápido, -20 = 20% mais lento) — diferente da escala de palavras por
    minuto usada pelo motor local."""
    async def _run():
        percent = rate or 0
        rate_str = f"+{percent}%" if percent >= 0 else f"{percent}%"
        communicate = edge_tts.Communicate(text, voice_id or "pt-BR-FranciscaNeural", rate=rate_str)
        await communicate.save(str(output_path))

    asyncio.run(_run())


def synthesize_speech(
    text: str,
    output_path: Path,
    engine: str = "local",
    rate: int | None = None,
    voice_id: str | None = None,
) -> None:
    if engine == "edge":
        synthesize_speech_edge(text, output_path, voice_id=voice_id, rate=rate)
    else:
        synthesize_speech_local(text, output_path, rate=rate, voice_id=voice_id)
