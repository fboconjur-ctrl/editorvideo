"""Renderiza uma lista de cortes (EDL — Edit Decision List) feita à mão na
timeline do editor: cada segmento é (start, end) em segundos, na ordem em
que devem aparecer no vídeo final (permite reordenar, diferente do corte
por silêncio/filler que só remove trechos mantendo a ordem original)."""
import subprocess
from pathlib import Path


def render_edl(input_path: Path, segments: list[tuple[float, float]], output_path: Path) -> None:
    if not segments:
        raise ValueError("Nenhum segmento para renderizar.")

    filter_parts = []
    concat_inputs = []
    for i, (start, end) in enumerate(segments):
        filter_parts.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]")
        filter_parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")

    concat_filter = "".join(concat_inputs) + f"concat=n={len(segments)}:v=1:a=1[outv][outa]"
    filter_complex = ";".join(filter_parts) + ";" + concat_filter

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
