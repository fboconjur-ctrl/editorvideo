"""Renderiza uma lista de cortes (EDL — Edit Decision List) feita à mão na
timeline do editor: cada segmento é (start, end) em segundos, na ordem em
que devem aparecer no vídeo final (permite reordenar, diferente do corte
por silêncio/filler que só remove trechos mantendo a ordem original).

Também suporta, por segmento, ajuste de velocidade/volume/filtro de cor
(as ferramentas "estilo CapCut"), e sobreposição de caixas de texto no
vídeo final já montado."""
import subprocess
from pathlib import Path
from typing import TypedDict

# Presets de filtro de cor por trecho.
COLOR_FILTERS = {
    "none": "",
    "vibrant": ",eq=saturation=1.4:contrast=1.1",
    "bw": ",hue=s=0",
    "warm": ",colorbalance=rs=0.15:gs=0.05",
    "cool": ",colorbalance=bs=0.15",
}


class RenderSegment(TypedDict):
    start: float
    end: float
    speed: float
    volume: float
    color_filter: str


class TextOverlay(TypedDict):
    text: str
    start: float
    end: float
    x_percent: float
    y_percent: float
    font_size: int
    color: str


def _escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "’")  # aspas retas viram tipográficas, evita escaping complicado
    text = text.replace("%", "\\%")
    return text


def render_edl(
    input_path: Path,
    segments: list[RenderSegment],
    texts: list[TextOverlay],
    output_path: Path,
) -> None:
    if not segments:
        raise ValueError("Nenhum segmento para renderizar.")

    filter_parts = []
    concat_inputs = []
    for i, seg in enumerate(segments):
        speed = max(0.5, min(2.0, seg.get("speed", 1.0) or 1.0))
        volume = max(0.0, seg.get("volume", 1.0))
        color_suffix = COLOR_FILTERS.get(seg.get("color_filter", "none"), "")

        filter_parts.append(
            f"[0:v]trim=start={seg['start']:.3f}:end={seg['end']:.3f},"
            f"setpts=(PTS-STARTPTS)/{speed}{color_suffix}[v{i}]"
        )
        filter_parts.append(
            f"[0:a]atrim=start={seg['start']:.3f}:end={seg['end']:.3f},"
            f"asetpts=PTS-STARTPTS,atempo={speed},volume={volume}[a{i}]"
        )
        concat_inputs.append(f"[v{i}][a{i}]")

    concat_filter = "".join(concat_inputs) + f"concat=n={len(segments)}:v=1:a=1[catv][outa]"
    filter_complex_parts = filter_parts + [concat_filter]

    last_video_label = "catv"
    for j, text in enumerate(texts):
        escaped = _escape_drawtext(text["text"])
        out_label = f"txt{j}"
        filter_complex_parts.append(
            f"[{last_video_label}]drawtext=text='{escaped}':"
            f"fontcolor={text.get('color', 'white')}:fontsize={text.get('font_size', 36)}:"
            f"x=(w*{text.get('x_percent', 50) / 100:.4f})-text_w/2:"
            f"y=(h*{text.get('y_percent', 85) / 100:.4f})-text_h/2:"
            f"enable='between(t,{text['start']:.3f},{text['end']:.3f})'[{out_label}]"
        )
        last_video_label = out_label

    filter_complex = ";".join(filter_complex_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", f"[{last_video_label}]", "-map", "[outa]",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
