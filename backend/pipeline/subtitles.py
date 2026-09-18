"""Geração de arquivos .srt e queima (burn-in) de legendas no vídeo."""
import subprocess
from pathlib import Path

from .ffprobe_utils import probe_dimensions
from .transcribe import Segment

# Alinhamento no padrão ASS/libass: 2 = embaixo centralizado, 8 = em cima
# centralizado, 5 = centro da tela.
POSITION_TO_ALIGNMENT = {
    "bottom": 2,
    "top": 8,
    "middle": 5,
}


def _format_timestamp(seconds: float) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    millis = int((secs - int(secs)) * 1000)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d},{millis:03d}"


def _wrap_caption_text(text: str, max_line_chars: int = 24) -> str:
    """Quebra o texto em linhas curtas (estilo legenda de rede social) em
    vez de deixar o libass decidir sozinho onde quebrar — com fonte grande
    e vídeo estreito (vertical), a quebra automática do libass gerava até
    5-6 linhas empilhadas pra uma frase só, com uma caixa de fundo em cada
    linha (visual "picotado", feio). Quebrando aqui em linhas de ~24
    caracteres, a legenda fica em no máximo 2-3 linhas curtas e legíveis."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        added_len = len(word) + (1 if current else 0)
        if current and current_len + added_len > max_line_chars:
            lines.append(" ".join(current))
            current, current_len = [], 0
        current.append(word)
        current_len += len(word) + (1 if len(current) > 1 else 0)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def resplit_segments_for_captions(segments: list[Segment], max_words: int = 7) -> list[Segment]:
    """Quebra segmentos longos (frases inteiras vindas do Whisper) em
    vários cues menores de no máximo `max_words` palavras cada, distribuindo
    o tempo proporcionalmente ao número de palavras — sem isso, uma frase
    de 20+ palavras vira uma legenda só, gigante, ocupando a tela inteira
    pela duração toda da frase. Cues menores e mais frequentes é o padrão
    de legenda usado em vídeo de rede social (CapCut, Captions.app etc)."""
    result: list[Segment] = []
    for seg in segments:
        words = seg.text.split()
        if len(words) <= max_words:
            result.append(seg)
            continue
        total_duration = seg.end - seg.start
        total_words = len(words)
        elapsed_words = 0
        for i in range(0, total_words, max_words):
            chunk_words = words[i : i + max_words]
            start = seg.start + total_duration * (elapsed_words / total_words)
            elapsed_words += len(chunk_words)
            end = seg.start + total_duration * (elapsed_words / total_words)
            result.append(Segment(start=start, end=end, text=" ".join(chunk_words)))
    return result


def write_srt(segments: list[Segment], srt_path: Path) -> None:
    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}")
        lines.append(_wrap_caption_text(seg.text))
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def burn_subtitles(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    font_size: int | None = None,
    position: str = "bottom",
) -> None:
    """Queima as legendas diretamente nos frames do vídeo via ffmpeg.

    `font_size=None` calcula um tamanho proporcional à altura do vídeo (em
    vez do tamanho fixo padrão do ffmpeg, que fica minúsculo em vídeos 4K
    e enorme em vídeos verticais pequenos).
    """
    width, height = probe_dimensions(video_path)
    if font_size is None:
        # Baseado na MENOR dimensão (não só a altura): num vídeo vertical
        # a largura é o fator limitante pra quantas palavras cabem numa
        # linha — usar só a altura (bem maior que a largura no vertical)
        # gerava fonte grande demais pra largura disponível, forçando
        # quebra em muitas linhas.
        font_size = max(16, round(min(width, height) / 18))

    alignment = POSITION_TO_ALIGNMENT.get(position, 2)
    margin_v = round(height * 0.06)

    # PlayResX/PlayResY dentro do force_style controlam diretamente o
    # sistema de coordenadas que o libass usa pra interpretar FontSize e
    # a largura de quebra de linha. Sem isso, o libass assume uma resolução
    # padrão (normalmente 384x288) bem menor que o vídeo real, o que faz o
    # texto quebrar em várias linhas e o bloco final ficar gigante. O
    # parâmetro `original_size` do filtro `subtitles` deveria fazer esse
    # ajuste automaticamente, mas na prática (testado) não tem efeito
    # nenhum nessa build do ffmpeg — por isso fixamos Play*Res explicitamente.
    #
    # BorderStyle=3 desenha uma caixa sólida atrás do texto (em vez de só
    # contorno) — texto branco sempre legível, independente da cor de
    # fundo do vídeo/imagem embaixo (contorno sozinho falha em fundos
    # muito claros, ex: céu, parede branca, roupa clara). Testado: o canal
    # alfa de BackColour não é respeitado nessa build do libass/ffmpeg
    # (sai sempre opaco), então usamos preto opaco direto em vez de fingir
    # uma transparência que não acontece.
    force_style = (
        f"FontSize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BackColour=&H00000000,"
        f"BorderStyle=3,Outline=1,Shadow=0,"
        f"Alignment={alignment},"
        f"MarginV={margin_v},"
        f"PlayResX={width},"
        f"PlayResY={height}"
    )

    srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf",
        f"subtitles='{srt_escaped}':force_style='{force_style}'",
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
