"""Separação por locutor ("quem fala quando") usando pyannote.audio.

Import pesado (PyTorch por baixo) feito de forma preguiçosa — só quando a
separação por locutor é realmente pedida — pra não deixar o servidor
inteiro mais lento/pesado de iniciar para quem não usa esse recurso."""
from pathlib import Path

from .transcribe import Segment


def diarize_speakers(audio_path: Path, hf_token: str) -> list[tuple[float, float, str]]:
    """Retorna uma lista de (início, fim, rótulo_bruto_do_locutor).

    Requer uma chave de acesso gratuita do Hugging Face (o modelo de
    diarização exige aceitar os termos de uso lá antes do primeiro uso).
    """
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError(
            "pyannote.audio não está instalado. Rode "
            "`pip install -r requirements.txt` no ambiente virtual do backend."
        ) from exc

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token)
    diarization = pipeline(str(audio_path))

    turns = []
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        turns.append((turn.start, turn.end, speaker))
    return turns


def label_segments_by_speaker(
    segments: list[Segment], turns: list[tuple[float, float, str]]
) -> list[tuple[str, Segment]]:
    """Atribui a cada segmento transcrito o locutor com maior sobreposição
    de tempo, e renomeia os rótulos brutos ("SPEAKER_00") para algo mais
    legível ("Pessoa 1"), na ordem em que aparecem pela primeira vez."""
    speaker_order: list[str] = []

    def _friendly_name(raw_label: str) -> str:
        if raw_label not in speaker_order:
            speaker_order.append(raw_label)
        return f"Pessoa {speaker_order.index(raw_label) + 1}"

    labeled: list[tuple[str, Segment]] = []
    for seg in segments:
        best_speaker = None
        best_overlap = 0.0
        for t_start, t_end, speaker in turns:
            overlap = min(seg.end, t_end) - max(seg.start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        label = _friendly_name(best_speaker) if best_speaker else "Pessoa ?"
        labeled.append((label, seg))
    return labeled


def format_labeled_transcript(labeled: list[tuple[str, Segment]]) -> str:
    """Agrupa falas consecutivas da mesma pessoa numa única linha, tipo:
    [Pessoa 1] Oi, tudo bem?
    [Pessoa 2] Tudo, e você?
    """
    lines: list[str] = []
    current_speaker: str | None = None
    buffer: list[str] = []

    for label, seg in labeled:
        if label != current_speaker:
            if buffer:
                lines.append(f"[{current_speaker}] {' '.join(buffer)}")
            current_speaker = label
            buffer = [seg.text]
        else:
            buffer.append(seg.text)

    if buffer:
        lines.append(f"[{current_speaker}] {' '.join(buffer)}")

    return "\n".join(lines)
