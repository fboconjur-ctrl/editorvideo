"""Correção automática de cor e normalização de áudio, tudo via filtros
nativos do ffmpeg (sem modelo de IA nenhum)."""
import json
import subprocess
from pathlib import Path

# Qualidade de saída: CRF 18 é visualmente sem perdas; áudio a 48 kHz/192k.
VIDEO_CODEC_ARGS = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
AUDIO_CODEC_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]

LOUDNORM_TARGET = "I=-16:TP=-1.5:LRA=11"


def _measure_loudness(input_path: Path) -> dict | None:
    """1ª passada do loudnorm: mede o áudio para aplicar ganho linear depois."""
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(input_path), "-vn",
        "-af", f"loudnorm={LOUDNORM_TARGET}:print_format=json", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr
    start, end = stderr.rfind("{"), stderr.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return None


def enhance(input_path: Path, output_path: Path) -> None:
    """Aplica em uma única passada de vídeo:

    - `normalize` com suavização temporal: corrige níveis de preto/branco
      sem fazer o brilho "pulsar" de um quadro para o outro.
    - `eq`: leve ganho de contraste/saturação para compensar vídeos "lavados".
    - `loudnorm` em duas passadas (modo linear): volume no padrão -16 LUFS
      sem o efeito de "bombeamento" do modo dinâmico.
    """
    # smoothing=60 quadros (~2 s a 30 fps) evita flicker; strength<1 preserva o look original.
    video_filter = "normalize=smoothing=60:strength=0.6,eq=contrast=1.05:saturation=1.08"

    m = _measure_loudness(input_path)
    if m:
        audio_filter = (
            f"loudnorm={LOUDNORM_TARGET}"
            f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true"
        )
    else:
        audio_filter = f"loudnorm={LOUDNORM_TARGET}"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", video_filter,
        "-af", audio_filter,
        *VIDEO_CODEC_ARGS,
        *AUDIO_CODEC_ARGS,
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
