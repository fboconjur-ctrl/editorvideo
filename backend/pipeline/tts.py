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


@dataclass
class WordTiming:
    text: str
    start: float
    end: float


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

# Lista fixa de reserva: usada quando a busca online da lista completa
# falha (rede lenta/instável, proxy bloqueando esse endpoint específico da
# Microsoft) — sem isso, o seletor de voz na interface fica só com
# "Padrão" e o usuário nunca descobre que existem outras vozes neurais
# além da default. Mantida sincronizada com o catálogo real (verificado
# via `edge_tts.list_voices()`) — a Microsoft descontinuou boa parte das
# vozes pt-BR que existiam antes; hoje só restam estas três.
_EDGE_FALLBACK_VOICES: list[VoiceInfo] = [
    VoiceInfo(id="pt-BR-FranciscaNeural", name="Francisca (feminina)", languages=["pt-BR"]),
    VoiceInfo(id="pt-BR-AntonioNeural", name="Antônio (masculina)", languages=["pt-BR"]),
    VoiceInfo(id="pt-BR-ThalitaMultilingualNeural", name="Thalita (feminina)", languages=["pt-BR"]),
]


async def list_edge_voices_async() -> list[VoiceInfo]:
    """Busca a lista de vozes reais direto da Microsoft. Precisa ser
    chamada com `await` de dentro de uma rota `async def` — nunca via
    `asyncio.run()`, que falha com "cannot be called from a running
    event loop" quando o servidor (uvicorn) já está com um loop rodando.
    Esse era o bug real por trás de vozes que davam "No audio was
    received": a versão antiga desta função sempre caía silenciosamente
    na lista fixa de reserva (o erro do asyncio.run era engolido por um
    `except Exception` genérico), e alguns IDs dessa lista fixa podem
    ter sido descontinuados pela Microsoft nesse meio tempo, causando
    falha só para essas vozes específicas na hora de sintetizar."""
    try:
        all_voices = await edge_tts.list_voices()
    except Exception:  # noqa: BLE001 - qualquer falha de rede cai pra lista fixa
        return _EDGE_FALLBACK_VOICES

    result = []
    for v in all_voices:
        if v["Locale"].startswith(_EDGE_LANG_PREFIXES):
            result.append(VoiceInfo(id=v["ShortName"], name=f"{v['FriendlyName']}", languages=[v["Locale"]]))
    return result or _EDGE_FALLBACK_VOICES


def list_edge_voices() -> list[VoiceInfo]:
    """Versão síncrona, para uso fora de uma rota async. Rotas `async def`
    da API devem usar `list_edge_voices_async` diretamente com `await`."""
    try:
        return asyncio.run(list_edge_voices_async())
    except RuntimeError:
        # Já existe um event loop rodando nesta thread — não há como
        # resolver isso de forma síncrona aqui, então cai na lista fixa.
        return _EDGE_FALLBACK_VOICES


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


def synthesize_speech_edge_with_words(
    text: str, output_path: Path, voice_id: str | None = None, rate: int | None = None
) -> list[WordTiming]:
    """Como `synthesize_speech_edge`, mas também devolve o tempo exato
    (início/fim, em segundos, relativo ao início do áudio) de cada
    palavra falada — usado pra gerar legenda animada estilo CapCut
    (palavra ganha destaque conforme é falada). Só o motor Edge fornece
    esse timing; o motor local (pyttsx3) não tem equivalente."""
    async def _run() -> list[WordTiming]:
        percent = rate or 0
        rate_str = f"+{percent}%" if percent >= 0 else f"{percent}%"
        # boundary="WordBoundary" é essencial aqui — o padrão da
        # biblioteca é "SentenceBoundary" (frase inteira, sem timing por
        # palavra); sem isso o stream nunca emite eventos "WordBoundary"
        # e a legenda karaokê sai sem nenhum texto (silenciosamente, sem
        # erro nenhum, porque a narração e o vídeo continuam sendo
        # gerados normalmente — só a legenda fica vazia).
        communicate = edge_tts.Communicate(
            text, voice_id or "pt-BR-FranciscaNeural", rate=rate_str, boundary="WordBoundary"
        )
        words: list[WordTiming] = []
        # 100-ns ("ticks") é a unidade que o serviço da Microsoft usa pra
        # offset/duration — precisa dividir por 10_000_000 pra virar segundos.
        TICKS_PER_SECOND = 10_000_000
        with output_path.open("wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio" and "data" in chunk:
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / TICKS_PER_SECOND
                    duration = chunk["duration"] / TICKS_PER_SECOND
                    words.append(WordTiming(text=chunk["text"], start=start, end=start + duration))
        return words

    return asyncio.run(_run())


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
