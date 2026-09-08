"""Detecção e remoção de palavras repetidas (gaguejo) e vícios de fala
("né", "tipo", "uhm"...), usando os timestamps por palavra do Whisper."""
import json
import re
import subprocess
from pathlib import Path

from .transcribe import Word, transcribe_words

# Vícios de fala comuns (pt-br e en) que quase nunca carregam significado e
# são seguros de remover isoladamente. Lista conservadora de propósito —
# evita cortar palavras ambíguas como "é" (verbo) ou "então" (conector válido
# em muitas frases).
DEFAULT_FILLER_WORDS = {
    "né", "ne", "ahn", "hmm", "uhm", "aham", "tipo", "um", "uh",
}


def _normalize(text: str) -> str:
    return re.sub(r"[^\w]", "", text.lower())


def _probe_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "0",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def find_removal_ranges(
    words: list[Word], filler_words: set[str] = DEFAULT_FILLER_WORDS
) -> list[tuple[float, float]]:
    """Retorna intervalos de tempo a cortar: repetições consecutivas da
    mesma palavra (mantém só a primeira ocorrência) e vícios de fala."""
    ranges: list[tuple[float, float]] = []
    previous_normalized = None

    for word in words:
        normalized = _normalize(word.text)
        if not normalized:
            continue

        if normalized == previous_normalized:
            ranges.append((word.start, word.end))
        elif normalized in filler_words:
            ranges.append((word.start, word.end))

        previous_normalized = normalized

    return ranges


def _build_keep_segments(
    duration: float, removal_ranges: list[tuple[float, float]], padding: float = 0.05
) -> list[tuple[float, float]]:
    padded = [(max(0.0, s - padding), min(duration, e + padding)) for s, e in removal_ranges]
    padded.sort()

    merged: list[list[float]] = []
    for start, end in padded:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    keep_segments = []
    cursor = 0.0
    for start, end in merged:
        if start > cursor:
            keep_segments.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keep_segments.append((cursor, duration))

    return keep_segments


def _cut_by_segments(input_path: Path, output_path: Path, keep_segments: list[tuple[float, float]]) -> None:
    select_expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in keep_segments)
    filter_complex = (
        f"[0:v]select='{select_expr}',setpts=N/FRAME_RATE/TB[v];"
        f"[0:a]aselect='{select_expr}',asetpts=N/SR/TB[a]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def remove_fillers(input_path: Path, output_path: Path) -> None:
    """Transcreve o vídeo, localiza repetições/vícios de fala e gera uma
    nova versão do vídeo com esses trechos removidos. Se nada for
    encontrado, apenas copia o vídeo original."""
    words = transcribe_words(input_path)
    removal_ranges = find_removal_ranges(words)

    if not removal_ranges:
        output_path.write_bytes(input_path.read_bytes())
        return

    duration = _probe_duration(input_path)
    keep_segments = _build_keep_segments(duration, removal_ranges)
    _cut_by_segments(input_path, output_path, keep_segments)
