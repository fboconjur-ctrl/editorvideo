"""Apresentação (PowerPoint) narrada: renderiza cada slide de um .pptx
como uma imagem e monta um vídeo onde o usuário escreve manualmente o
texto que vai ser falado em cada slide (sem nenhuma busca automática de
mídia — a "imagem" de cada trecho já é o próprio slide).

A conversão pptx -> imagens usa o LibreOffice (headless, só pra
renderizar o slide fielmente — não precisa estar aberto/visível) pra
gerar um PDF, e depois a biblioteca PyMuPDF pra transformar cada página
do PDF numa imagem PNG. Isso evita reimplementar um renderizador de
slides (fontes, temas, gráficos, imagens embutidas) do zero."""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

from .ffprobe_utils import probe_duration
from .subtitles import build_karaoke_ass, burn_karaoke_subtitles, burn_subtitles, write_srt
from .text_to_video import (
    FPS,
    HORIZONTAL_RESOLUTION,
    VERTICAL_RESOLUTION,
    _build_segment_from_image,
    apply_webcam_overlay,
    build_bumper_from_video,
)
from .transcribe import Segment
from .tts import WordTiming, synthesize_speech, synthesize_speech_edge_with_words


class SlidesConversionError(Exception):
    """Erro ao converter o .pptx em imagens (ex: LibreOffice não
    instalado/encontrado no PATH)."""


def render_pptx_to_images(pptx_path: Path, out_dir: Path, dpi: int = 150) -> list[Path]:
    if shutil.which("soffice") is None:
        raise SlidesConversionError(
            "LibreOffice não foi encontrado no PATH. Instale gratuitamente em "
            "https://www.libreoffice.org/download/download/ e tente de novo "
            "(precisa apenas estar instalado, não abrir o programa)."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        cmd = [
            "soffice", "--headless", "--norestore",
            "--convert-to", "pdf", "--outdir", str(tmp), str(pptx_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        pdf_candidates = list(tmp.glob("*.pdf"))
        if result.returncode != 0 or not pdf_candidates:
            raise SlidesConversionError(
                f"Falha ao converter a apresentação com o LibreOffice: {result.stderr or result.stdout}"
            )
        pdf_path = pdf_candidates[0]

        doc = pymupdf.open(pdf_path)
        image_paths: list[Path] = []
        try:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=dpi)
                image_path = out_dir / f"slide_{i:03d}.png"
                pix.save(str(image_path))
                image_paths.append(image_path)
        finally:
            doc.close()

    if not image_paths:
        raise SlidesConversionError("A apresentação não tem nenhum slide.")
    return image_paths


def generate_video_from_slides(
    slide_image_paths: list[Path],
    narrations: list[str],
    output_path: Path,
    tts_engine: str = "edge",
    voice_id: str | None = None,
    rate: int | None = None,
    subtitles_enabled: bool = False,
    subtitle_font_size: int | None = None,
    subtitle_position: str = "bottom",
    subtitle_style: str = "static",
    orientation: str = "horizontal",
    intro_video_path: Path | None = None,
    outro_video_path: Path | None = None,
    webcam_video_path: Path | None = None,
    webcam_position: str = "bottom-right",
) -> None:
    """Como `text_to_video.generate_video_from_text`, mas sem nenhuma
    divisão automática de texto nem busca de mídia: cada slide já É um
    trecho (com seu próprio texto de narração escrito pelo usuário) e já
    tem sua imagem definida (o próprio slide renderizado). Slides com
    narração vazia são pulados (ex: slide de transição/capa sem fala)."""
    if len(slide_image_paths) != len(narrations):
        raise ValueError("Número de slides e de textos de narração não bate.")

    pairs = [(img, text.strip()) for img, text in zip(slide_image_paths, narrations) if text.strip()]
    if not pairs:
        raise ValueError("Nenhum slide tem texto de narração preenchido.")

    resolution = VERTICAL_RESOLUTION if orientation == "vertical" else HORIZONTAL_RESOLUTION
    karaoke_active = subtitles_enabled and subtitle_style == "karaoke" and tts_engine == "edge"

    subtitle_segments: list[Segment] = []
    karaoke_chunks: list[list[WordTiming]] = []
    elapsed = 0.0

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        content_segment_paths = []

        for i, (image_path, text) in enumerate(pairs):
            audio_path = tmp / f"audio_{i}.mp3"
            if karaoke_active:
                words = synthesize_speech_edge_with_words(text, audio_path, voice_id=voice_id, rate=rate)
                karaoke_chunks.append(
                    [WordTiming(text=w.text, start=elapsed + w.start, end=elapsed + w.end) for w in words]
                )
            else:
                synthesize_speech(text, audio_path, engine=tts_engine, voice_id=voice_id, rate=rate)
            duration = probe_duration(audio_path)
            subtitle_segments.append(Segment(start=elapsed, end=elapsed + duration, text=text))
            elapsed += duration

            segment_path = tmp / f"segment_{i}.mp4"
            _build_segment_from_image(image_path, audio_path, duration, segment_path, resolution=resolution)
            content_segment_paths.append(segment_path)

        content_concat = tmp / "content_concat.mp4"
        content_list = tmp / "content_concat.txt"
        content_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in content_segment_paths), encoding="utf-8"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(content_list), "-c", "copy", str(content_concat)],
            check=True, capture_output=True, text=True,
        )
        content_current = content_concat

        if karaoke_active and not any(karaoke_chunks):
            karaoke_active = False

        if karaoke_active:
            ass_path = tmp / "legendas.ass"
            build_karaoke_ass(
                karaoke_chunks, ass_path, resolution,
                font_size=subtitle_font_size, position=subtitle_position,
            )
            content_with_subs = tmp / "content_with_subs.mp4"
            burn_karaoke_subtitles(content_current, ass_path, content_with_subs)
            content_current = content_with_subs
        elif subtitles_enabled:
            srt_path = tmp / "legendas.srt"
            write_srt(subtitle_segments, srt_path)
            content_with_subs = tmp / "content_with_subs.mp4"
            burn_subtitles(
                content_current, srt_path, content_with_subs,
                font_size=subtitle_font_size, position=subtitle_position,
            )
            content_current = content_with_subs

        if webcam_video_path:
            content_with_webcam = tmp / "content_with_webcam.mp4"
            apply_webcam_overlay(
                content_current, webcam_video_path, content_with_webcam,
                resolution=resolution, position=webcam_position,
            )
            content_current = content_with_webcam

        final_segment_paths = []
        if intro_video_path:
            intro_segment_path = tmp / "intro.mp4"
            build_bumper_from_video(intro_video_path, intro_segment_path, resolution=resolution)
            final_segment_paths.append(intro_segment_path)

        final_segment_paths.append(content_current)

        if outro_video_path:
            outro_segment_path = tmp / "outro.mp4"
            build_bumper_from_video(outro_video_path, outro_segment_path, resolution=resolution)
            final_segment_paths.append(outro_segment_path)

        if len(final_segment_paths) == 1:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(content_current), "-c", "copy", "-movflags", "+faststart", str(output_path)],
                check=True, capture_output=True, text=True,
            )
        else:
            final_list = tmp / "final_concat.txt"
            final_list.write_text(
                "\n".join(f"file '{p.as_posix()}'" for p in final_segment_paths), encoding="utf-8"
            )
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(final_list),
                 "-c", "copy", "-movflags", "+faststart", str(output_path)],
                check=True, capture_output=True, text=True,
            )
