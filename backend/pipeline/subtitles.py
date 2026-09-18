"""Geração de arquivos .srt/.ass e queima (burn-in) de legendas no vídeo."""
import subprocess
from pathlib import Path

from .ffprobe_utils import probe_dimensions
from .transcribe import Segment
from .tts import WordTiming

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


def _ass_timestamp(seconds: float) -> str:
    # Arredonda tudo pra centésimos de segundo ANTES de quebrar em
    # horas/minutos/segundos — evita casos de borda onde arredondar só a
    # parte decimal estoura pro próximo minuto/hora sem propagar o carry
    # (ex: 59.999s virando "0:00:60.00" em vez de "0:01:00.00").
    total_centis = round(max(0.0, seconds) * 100)
    hours, rem = divmod(total_centis, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, centis = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _escape_ass_text(text: str) -> str:
    # Chaves têm significado especial no ASS (abrem/fecham tags de estilo)
    # — sem isso, uma palavra com "{" ou "}" (raro, mas possível em texto
    # colado de outro lugar) quebraria a legenda inteira dali pra frente.
    return text.replace("{", "(").replace("}", ")")


def build_karaoke_ass(
    chunk_word_timings: list[list[WordTiming]],
    ass_path: Path,
    resolution: tuple[int, int],
    font_size: int | None = None,
    position: str = "bottom",
) -> None:
    """Gera um arquivo .ass com efeito karaokê nativo do libass: cada
    trecho narrado vira uma linha de legenda onde as palavras mudam de
    cor conforme são faladas (destaque progressivo), igual ao estilo de
    legenda animada do CapCut/Captions.app — sem precisar desenhar frame
    a frame, o próprio libass anima a transição de cor no tempo certo.

    `chunk_word_timings`: uma lista por trecho narrado, cada uma com o
    tempo (já absoluto, em segundos, na linha do tempo do vídeo final) de
    cada palavra daquele trecho. Normalmente vem do timing de palavra do
    motor de voz Edge (`synthesize_speech_edge_with_words`) — o motor
    local não fornece esse timing."""
    width, height = resolution
    if font_size is None:
        font_size = max(16, round(min(width, height) / 18))

    alignment = POSITION_TO_ALIGNMENT.get(position, 2)
    margin_v = round(height * 0.06)

    # Cores no formato ASS &HAABBGGRR (alfa, azul, verde, vermelho).
    # Antes de ser falada: branco. Depois de falada: azul de destaque
    # (mesmo tom de accent usado na interface, #5b7cff -> BGR ff7c5b).
    secondary_unspoken = "&H00FFFFFF"
    primary_spoken = "&H00FF7C5B"
    outline_color = "&H00000000"
    back_color = "&H00000000"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Karaoke,Arial,{font_size},{primary_spoken},{secondary_unspoken},{outline_color},{back_color},"
        f"1,0,0,0,100,100,0,0,3,1,0,{alignment},10,10,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines = [header]
    for words in chunk_word_timings:
        if not words:
            continue
        start = words[0].start
        end = words[-1].end
        karaoke_text = "".join(
            f"{{\\k{max(1, round((w.end - w.start) * 100))}}}{_escape_ass_text(w.text)} " for w in words
        ).rstrip()
        lines.append(f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Karaoke,,0,0,0,,{karaoke_text}\n")

    ass_path.write_text("".join(lines), encoding="utf-8")


def burn_karaoke_subtitles(video_path: Path, ass_path: Path, output_path: Path) -> None:
    """Queima o arquivo .ass (com efeito karaokê já definido dentro dele)
    no vídeo. Diferente de `burn_subtitles`, não usa `force_style` — o
    estilo (cor, tamanho, posição, PlayResX/Y) já vem definido no próprio
    arquivo .ass gerado por `build_karaoke_ass`."""
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
