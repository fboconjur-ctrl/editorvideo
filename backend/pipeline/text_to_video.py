"""Gera um vídeo tipo slideshow narrado a partir de um texto: divide o
texto em trechos, narra cada um (TTS), busca uma foto relacionada no banco
gratuito Pexels para cada trecho, e monta tudo num vídeo com efeito de
zoom lento (Ken Burns), sincronizado com o áudio de cada trecho."""
import re
import subprocess
import tempfile
from pathlib import Path

import requests
import yake
from deep_translator import GoogleTranslator

from .ffprobe_utils import probe_duration
from .tts import synthesize_speech

RESOLUTION = (1920, 1080)
FPS = 25
MAX_WORDS_PER_CHUNK = 22

_yake_extractor = yake.KeywordExtractor(lan="pt", n=2, top=3, dedupLim=0.9)


def extract_keyphrase(chunk_text: str) -> str:
    """Usa YAKE (extração estatística de palavras-chave, leve, sem baixar
    modelo) pra achar a frase-chave mais relevante do trecho em português
    — bem melhor do que filtrar stopwords manualmente, porque o YAKE
    reconhece expressões compostas como unidade ("tribunal eleitoral" e
    "tribunal militar" saem como frases distintas, não como palavras
    soltas embaralhadas)."""
    keywords = _yake_extractor.extract_keywords(chunk_text)
    if not keywords:
        return chunk_text
    # keywords vem ordenado por relevância (score menor = mais relevante)
    best_phrase, _score = min(keywords, key=lambda kw: kw[1])
    return best_phrase


def translate_to_english(text: str) -> str:
    """O catálogo/índice do Pexels responde muito melhor a termos em
    inglês. Traduz só a frase-chave já extraída (curta, então a chamada
    de tradução é rápida) preservando o contexto da expressão — ex:
    "tribunal eleitoral" vira corretamente "electoral court". Se a
    tradução falhar (ex: sem internet no momento), usa a frase-chave em
    português mesmo como fallback — ainda assim específica o bastante
    pra buscar uma foto razoável."""
    try:
        translated = GoogleTranslator(source="pt", target="en").translate(text[:100])
        return translated or text
    except Exception:  # noqa: BLE001 - tradução é best-effort
        return text


def split_into_chunks(text: str, max_words: int = MAX_WORDS_PER_CHUNK) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and current_words + words > max_words:
            chunks.append(" ".join(current))
            current, current_words = [], 0
        current.append(sentence)
        current_words += words
    if current:
        chunks.append(" ".join(current))
    return chunks


def search_pexels_image(chunk_text: str, api_key: str) -> tuple[bytes | None, str]:
    """Retorna (bytes da imagem ou None, query usada na busca) — a query é
    devolvida mesmo em caso de falha, para poder ser registrada num log de
    diagnóstico."""
    keyphrase_pt = extract_keyphrase(chunk_text)
    query = translate_to_english(keyphrase_pt)
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query[:80], "per_page": 1, "orientation": "landscape"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return None, query
        image_resp = requests.get(photos[0]["src"]["large"], timeout=15)
        image_resp.raise_for_status()
        return image_resp.content, query
    except requests.RequestException:
        return None, query


def _build_segment_from_image(image_path: Path, audio_path: Path, duration: float, output_path: Path) -> None:
    w, h = RESOLUTION
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"zoompan=z='min(zoom+0.0008,1.08)':d={int(duration * FPS)}:s={w}x{h}:fps={FPS}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _build_segment_solid_color(audio_path: Path, duration: float, output_path: Path) -> None:
    """Usado quando nenhuma foto relacionada foi encontrada — fundo sólido
    em vez de travar a geração do vídeo."""
    w, h = RESOLUTION
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x1d1f27:s={w}x{h}:d={duration:.3f}",
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def generate_video_from_text(
    text: str,
    output_path: Path,
    pexels_api_key: str,
    tts_engine: str = "edge",
    voice_id: str | None = None,
    rate: int | None = None,
) -> None:
    chunks = split_into_chunks(text)
    if not chunks:
        raise ValueError("Texto vazio.")

    query_log_lines = []

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        segment_paths = []

        for i, chunk in enumerate(chunks):
            audio_path = tmp / f"audio_{i}.mp3"
            synthesize_speech(chunk, audio_path, engine=tts_engine, voice_id=voice_id, rate=rate)
            duration = probe_duration(audio_path)

            segment_path = tmp / f"segment_{i}.mp4"
            image_bytes, used_query = (
                search_pexels_image(chunk, pexels_api_key) if pexels_api_key else (None, "")
            )
            query_log_lines.append(f"[{i}] busca=\"{used_query}\" | trecho=\"{chunk}\"")
            if image_bytes:
                image_path = tmp / f"image_{i}.jpg"
                image_path.write_bytes(image_bytes)
                _build_segment_from_image(image_path, audio_path, duration, segment_path)
            else:
                _build_segment_solid_color(audio_path, duration, segment_path)

            segment_paths.append(segment_path)

        concat_list = tmp / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segment_paths), encoding="utf-8"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    log_path = output_path.parent / "buscas_de_imagem.log.txt"
    log_path.write_text("\n".join(query_log_lines), encoding="utf-8")
