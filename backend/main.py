"""API local do editor de vídeo automático. Nenhuma chamada externa é feita:
todo o processamento (corte de silêncio, transcrição, legendas) roda na
própria máquina."""
import json
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.background_removal import remove_background
from pipeline.diarization import diarize_speakers, format_labeled_transcript, label_segments_by_speaker
from pipeline.enhance import enhance
from pipeline.ffprobe_utils import probe_duration
from pipeline.filler_removal import remove_fillers
from pipeline.reframe import reframe_vertical
from pipeline.silence_cut import cut_silence
from pipeline.stabilize import stabilize
from pipeline.subtitles import burn_subtitles, resplit_segments_for_captions, write_srt
from pipeline.timeline_render import render_edl
from pipeline.transcribe import transcribe
from pipeline.settings_store import (
    get_huggingface_token,
    get_pexels_api_key,
    set_huggingface_token,
    set_pexels_api_key,
)
from pipeline.text_to_video import (
    HORIZONTAL_RESOLUTION,
    VERTICAL_RESOLUTION,
    build_cover_thumbnail,
    generate_video_from_text,
    split_into_chunks,
)
from pipeline.bumpers import (
    add_webcam_clip,
    get_bumper_path,
    get_random_webcam_clip,
    list_webcam_clips,
    remove_bumper,
    remove_webcam_clip,
    save_bumper,
)
from pipeline.tts import list_edge_voices, list_local_voices, synthesize_speech
from pipeline.upscale import upscale
from pipeline.youtube import download_audio

BASE_DIR = Path(__file__).parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Video Editor Local")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JobStatus = Literal[
    "queued",
    "cutting_silence",
    "removing_fillers",
    "stabilizing",
    "enhancing",
    "removing_background",
    "reframing_vertical",
    "upscaling",
    "transcribing",
    "generating_subtitles",
    "done",
    "error",
]


class Job(BaseModel):
    id: str
    status: JobStatus = "queued"
    progress_detail: str | None = None
    error: str | None = None
    result_video: str | None = None
    result_srt: str | None = None


JOBS: dict[str, Job] = {}


def _run_pipeline(
    job_id: str,
    cut_silence_enabled: bool,
    remove_fillers_enabled: bool,
    stabilize_enabled: bool,
    enhance_enabled: bool,
    reframe_enabled: bool,
    remove_bg_enabled: bool,
    background_color: str | None,
    upscale_enabled: bool,
    subtitles_enabled: bool,
    burn_in: bool,
    subtitle_font_size: int | None,
    subtitle_position: str,
) -> None:
    job = JOBS[job_id]
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    current_video = UPLOADS_DIR / job_id / "input.mp4"

    try:
        if cut_silence_enabled:
            job.status = "cutting_silence"
            cut_video = job_dir / "cut.mp4"
            cut_silence(current_video, cut_video)
            current_video = cut_video

        if remove_fillers_enabled:
            job.status = "removing_fillers"
            no_fillers_video = job_dir / "no_fillers.mp4"
            remove_fillers(current_video, no_fillers_video)
            current_video = no_fillers_video

        if stabilize_enabled:
            job.status = "stabilizing"
            stabilized_video = job_dir / "stabilized.mp4"
            stabilize(current_video, stabilized_video)
            current_video = stabilized_video

        if enhance_enabled:
            job.status = "enhancing"
            enhanced_video = job_dir / "enhanced.mp4"
            enhance(current_video, enhanced_video)
            current_video = enhanced_video

        if reframe_enabled:
            job.status = "reframing_vertical"
            reframed_video = job_dir / "reframed.mp4"
            reframe_vertical(current_video, reframed_video)
            current_video = reframed_video

        if remove_bg_enabled:
            job.status = "removing_background"
            bg_output_ext = "mp4" if background_color else "webm"
            bg_video = job_dir / f"no_bg.{bg_output_ext}"

            def _on_bg_progress(done: int, total: int) -> None:
                job.progress_detail = f"frame {done}/{total}"

            remove_background(
                current_video, bg_video, job_dir / "bg_tmp",
                background_color=background_color or None,
                progress_callback=_on_bg_progress,
            )
            job.progress_detail = None
            current_video = bg_video

        if upscale_enabled:
            job.status = "upscaling"
            upscaled_video = job_dir / "upscaled.mp4"
            upscale(current_video, upscaled_video)
            current_video = upscaled_video

        srt_path = None
        if subtitles_enabled:
            job.status = "transcribing"
            segments = transcribe(current_video)

            job.status = "generating_subtitles"
            srt_path = job_dir / "legendas.srt"
            write_srt(resplit_segments_for_captions(segments), srt_path)

            if burn_in:
                final_video = job_dir / "final.mp4"
                burn_subtitles(
                    current_video, srt_path, final_video,
                    font_size=subtitle_font_size, position=subtitle_position,
                )
                current_video = final_video

        final_output = job_dir / f"resultado{current_video.suffix}"
        if current_video != final_output:
            shutil.copy(current_video, final_output)

        job.result_video = str(final_output)
        job.result_srt = str(srt_path) if srt_path else None
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 - queremos capturar qualquer falha do pipeline
        job.status = "error"
        job.error = str(exc)


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    cut_silence_enabled: bool = Form(True),
    remove_fillers_enabled: bool = Form(False),
    stabilize_enabled: bool = Form(False),
    enhance_enabled: bool = Form(True),
    reframe_enabled: bool = Form(False),
    remove_bg_enabled: bool = Form(False),
    background_color: str = Form(""),
    upscale_enabled: bool = Form(False),
    subtitles_enabled: bool = Form(True),
    burn_in: bool = Form(True),
    subtitle_font_size: int = Form(0),
    subtitle_position: str = Form("bottom"),
) -> Job:
    job_id = str(uuid.uuid4())
    job_upload_dir = UPLOADS_DIR / job_id
    job_upload_dir.mkdir(parents=True)

    input_path = job_upload_dir / "input.mp4"
    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    job = Job(id=job_id)
    JOBS[job_id] = job

    background_tasks.add_task(
        _run_pipeline,
        job_id,
        cut_silence_enabled,
        remove_fillers_enabled,
        stabilize_enabled,
        enhance_enabled,
        reframe_enabled,
        remove_bg_enabled,
        background_color.strip() or None,
        upscale_enabled,
        subtitles_enabled,
        burn_in,
        subtitle_font_size or None,
        subtitle_position,
    )
    return job


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> Job:
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}/video")
async def download_video(job_id: str) -> FileResponse:
    job = JOBS[job_id]
    result_path = Path(job.result_video)
    return FileResponse(result_path, filename=f"resultado{result_path.suffix}")


@app.get("/api/jobs/{job_id}/subtitles")
async def download_subtitles(job_id: str) -> FileResponse:
    job = JOBS[job_id]
    return FileResponse(job.result_srt, filename="legendas.srt")


# --- Editor manual (timeline) ---------------------------------------------
# Fluxo independente do pipeline automático acima: aqui o vídeo é só
# armazenado (sem processamento), o usuário decide os cortes na interface,
# e o backend renderiza a lista de cortes (EDL) quando pedido.


class UploadInfo(BaseModel):
    upload_id: str
    duration: float


@app.post("/api/uploads")
async def create_upload(file: UploadFile = File(...)) -> UploadInfo:
    upload_id = str(uuid.uuid4())
    upload_dir = UPLOADS_DIR / upload_id
    upload_dir.mkdir(parents=True)

    input_path = upload_dir / "input.mp4"
    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    return UploadInfo(upload_id=upload_id, duration=probe_duration(input_path))


@app.get("/api/uploads/{upload_id}/video")
async def get_upload_video(upload_id: str) -> FileResponse:
    return FileResponse(UPLOADS_DIR / upload_id / "input.mp4")


@app.post("/api/jobs/{job_id}/promote")
async def promote_job_to_upload(job_id: str) -> UploadInfo:
    """Pega o resultado de um job do pipeline automático já concluído e
    disponibiliza como um novo "upload", pronto para abrir no editor
    manual (timeline) e continuar editando em cima dele."""
    job = JOBS[job_id]
    if job.status != "done" or not job.result_video:
        raise HTTPException(status_code=400, detail="O job ainda não foi concluído.")

    upload_id = str(uuid.uuid4())
    upload_dir = UPLOADS_DIR / upload_id
    upload_dir.mkdir(parents=True)

    input_path = upload_dir / "input.mp4"
    shutil.copy(job.result_video, input_path)

    return UploadInfo(upload_id=upload_id, duration=probe_duration(input_path))


class EdlSegment(BaseModel):
    start: float
    end: float
    speed: float = 1.0
    volume: float = 1.0
    color_filter: str = "none"


class TextOverlayRequest(BaseModel):
    text: str
    start: float
    end: float
    x_percent: float = 50.0
    y_percent: float = 85.0
    font_size: int = 36
    color: str = "white"


class RenderRequest(BaseModel):
    upload_id: str
    segments: list[EdlSegment]
    texts: list[TextOverlayRequest] = []


RenderStatus = Literal["queued", "rendering", "done", "error"]


class RenderJob(BaseModel):
    id: str
    status: RenderStatus = "queued"
    error: str | None = None
    result_video: str | None = None


RENDER_JOBS: dict[str, RenderJob] = {}


def _run_render(
    job_id: str,
    upload_id: str,
    segments: list[dict],
    texts: list[dict],
) -> None:
    job = RENDER_JOBS[job_id]
    try:
        job.status = "rendering"
        input_path = UPLOADS_DIR / upload_id / "input.mp4"
        job_dir = OUTPUTS_DIR / job_id
        job_dir.mkdir(exist_ok=True)
        output_path = job_dir / "resultado.mp4"

        render_edl(input_path, segments, texts, output_path)

        job.result_video = str(output_path)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 - queremos capturar qualquer falha da renderização
        job.status = "error"
        job.error = str(exc)


@app.post("/api/render")
async def create_render(background_tasks: BackgroundTasks, request: RenderRequest) -> RenderJob:
    job_id = str(uuid.uuid4())
    job = RenderJob(id=job_id)
    RENDER_JOBS[job_id] = job

    segments = [
        {
            "start": s.start, "end": s.end,
            "speed": s.speed, "volume": s.volume, "color_filter": s.color_filter,
        }
        for s in request.segments
    ]
    texts = [
        {
            "text": t.text, "start": t.start, "end": t.end,
            "x_percent": t.x_percent, "y_percent": t.y_percent,
            "font_size": t.font_size, "color": t.color,
        }
        for t in request.texts
    ]
    background_tasks.add_task(_run_render, job_id, request.upload_id, segments, texts)
    return job


@app.get("/api/render/{job_id}")
async def get_render(job_id: str) -> RenderJob:
    return RENDER_JOBS[job_id]


@app.get("/api/render/{job_id}/video")
async def download_render(job_id: str) -> FileResponse:
    job = RENDER_JOBS[job_id]
    return FileResponse(job.result_video, filename="resultado.mp4")


# --- Transcrição avulsa ----------------------------------------------------
# Sobe um vídeo/áudio e recebe de volta um .txt e um .srt, sem rodar
# nenhuma outra etapa do pipeline.

TranscriptionStatus = Literal[
    "queued", "downloading", "transcribing", "identifying_speakers", "done", "error"
]


class TranscriptionJob(BaseModel):
    id: str
    status: TranscriptionStatus = "queued"
    error: str | None = None
    result_txt: str | None = None
    result_srt: str | None = None


TRANSCRIPTION_JOBS: dict[str, TranscriptionJob] = {}


def _run_transcription(job_id: str, input_path: Path, diarize: bool = False) -> None:
    job = TRANSCRIPTION_JOBS[job_id]
    try:
        job.status = "transcribing"
        segments = transcribe(input_path)

        job_dir = OUTPUTS_DIR / job_id
        job_dir.mkdir(exist_ok=True)

        if diarize:
            job.status = "identifying_speakers"
            hf_token = get_huggingface_token()
            if not hf_token:
                raise RuntimeError(
                    "Separação por locutor precisa de uma chave gratuita do Hugging Face configurada."
                )
            turns = diarize_speakers(input_path, hf_token)
            labeled = label_segments_by_speaker(segments, turns)
            txt_content = format_labeled_transcript(labeled)
        else:
            txt_content = "\n".join(s.text for s in segments)

        txt_path = job_dir / "transcricao.txt"
        txt_path.write_text(txt_content, encoding="utf-8")

        srt_path = job_dir / "transcricao.srt"
        write_srt(segments, srt_path)

        job.result_txt = str(txt_path)
        job.result_srt = str(srt_path)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


def _run_youtube_transcription(job_id: str, input_path: Path, url: str, diarize: bool) -> None:
    job = TRANSCRIPTION_JOBS[job_id]
    try:
        job.status = "downloading"
        download_audio(url, input_path)
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = f"Falha ao baixar áudio do YouTube: {exc}"
        return
    _run_transcription(job_id, input_path, diarize=diarize)


@app.post("/api/transcriptions")
async def create_transcription(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    youtube_url: str = Form(""),
    diarize: bool = Form(False),
) -> TranscriptionJob:
    youtube_url = youtube_url.strip()
    if not file and not youtube_url:
        raise HTTPException(status_code=400, detail="Envie um arquivo ou um link do YouTube.")

    job_id = str(uuid.uuid4())
    upload_dir = UPLOADS_DIR / job_id
    upload_dir.mkdir(parents=True)
    input_path = upload_dir / "input.mp4"

    job = TranscriptionJob(id=job_id)
    TRANSCRIPTION_JOBS[job_id] = job

    if youtube_url:
        background_tasks.add_task(_run_youtube_transcription, job_id, input_path, youtube_url, diarize)
    else:
        with input_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        background_tasks.add_task(_run_transcription, job_id, input_path, diarize)

    return job


@app.get("/api/transcriptions/{job_id}")
async def get_transcription(job_id: str) -> TranscriptionJob:
    return TRANSCRIPTION_JOBS[job_id]


@app.get("/api/transcriptions/{job_id}/txt")
async def download_transcription_txt(job_id: str) -> FileResponse:
    job = TRANSCRIPTION_JOBS[job_id]
    return FileResponse(job.result_txt, filename="transcricao.txt")


@app.get("/api/transcriptions/{job_id}/srt")
async def download_transcription_srt(job_id: str) -> FileResponse:
    job = TRANSCRIPTION_JOBS[job_id]
    return FileResponse(job.result_srt, filename="transcricao.srt")


# --- Texto para voz (TTS) ---------------------------------------------------

TtsStatus = Literal["queued", "generating", "done", "error"]


class TtsJob(BaseModel):
    id: str
    status: TtsStatus = "queued"
    error: str | None = None
    result_audio: str | None = None


TTS_JOBS: dict[str, TtsJob] = {}


def _run_tts(job_id: str, text: str, engine: str, rate: int | None, voice_id: str | None) -> None:
    job = TTS_JOBS[job_id]
    try:
        job.status = "generating"
        job_dir = OUTPUTS_DIR / job_id
        job_dir.mkdir(exist_ok=True)
        output_path = job_dir / "voz.wav"

        synthesize_speech(text, output_path, engine=engine, rate=rate, voice_id=voice_id)

        job.result_audio = str(output_path)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


class VoiceOption(BaseModel):
    id: str
    name: str
    languages: list[str]


@app.get("/api/tts/voices")
async def get_voices(engine: str = "local") -> list[VoiceOption]:
    voices = list_edge_voices() if engine == "edge" else list_local_voices()
    return [VoiceOption(id=v.id, name=v.name, languages=v.languages) for v in voices]


@app.post("/api/tts")
async def create_tts(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    engine: str = Form("local"),
    rate: int = Form(0),
    voice_id: str = Form(""),
) -> TtsJob:
    job_id = str(uuid.uuid4())
    job = TtsJob(id=job_id)
    TTS_JOBS[job_id] = job
    background_tasks.add_task(_run_tts, job_id, text, engine, rate or None, voice_id.strip() or None)
    return job


@app.get("/api/tts/{job_id}")
async def get_tts(job_id: str) -> TtsJob:
    return TTS_JOBS[job_id]


@app.get("/api/tts/{job_id}/audio")
async def download_tts(job_id: str) -> FileResponse:
    job = TTS_JOBS[job_id]
    return FileResponse(job.result_audio, filename="voz.wav")


# --- Configurações locais (chave de API do Pexels) --------------------------


class SettingsInfo(BaseModel):
    has_pexels_key: bool
    has_huggingface_token: bool


class SettingsUpdate(BaseModel):
    pexels_api_key: str | None = None
    huggingface_token: str | None = None


def _settings_info() -> SettingsInfo:
    return SettingsInfo(
        has_pexels_key=bool(get_pexels_api_key()),
        has_huggingface_token=bool(get_huggingface_token()),
    )


@app.get("/api/settings")
async def get_settings() -> SettingsInfo:
    return _settings_info()


@app.post("/api/settings")
async def update_settings(payload: SettingsUpdate) -> SettingsInfo:
    if payload.pexels_api_key is not None:
        set_pexels_api_key(payload.pexels_api_key.strip())
    if payload.huggingface_token is not None:
        set_huggingface_token(payload.huggingface_token.strip())
    return _settings_info()


# --- Texto para vídeo (narração + fotos automáticas) ------------------------

TextToVideoStatus = Literal["queued", "generating", "done", "error"]


class TextToVideoJob(BaseModel):
    id: str
    status: TextToVideoStatus = "queued"
    error: str | None = None
    result_video: str | None = None
    result_log: str | None = None
    result_thumbnail: str | None = None


TEXT_TO_VIDEO_JOBS: dict[str, TextToVideoJob] = {}


@app.post("/api/text-to-video/chunks")
async def preview_text_to_video_chunks(text: str = Form(...)) -> list[str]:
    """Devolve como o texto vai ser dividido em trechos, sem gerar nada —
    usado pela interface pra deixar o usuário escolher manualmente qual
    imagem vai em qual trecho, em vez de adivinhar uma ordem/ciclo."""
    return split_into_chunks(text)


class BumperStatus(BaseModel):
    has_intro: bool
    has_outro: bool
    webcam_clips: list[str]


def _bumpers_status() -> BumperStatus:
    return BumperStatus(
        has_intro=get_bumper_path("intro") is not None,
        has_outro=get_bumper_path("outro") is not None,
        webcam_clips=[p.name for p in list_webcam_clips()],
    )


@app.get("/api/text-to-video/bumpers")
async def get_bumpers_status() -> BumperStatus:
    return _bumpers_status()


@app.post("/api/text-to-video/bumpers")
async def upload_bumpers(
    intro_video: UploadFile | None = File(None),
    outro_video: UploadFile | None = File(None),
) -> BumperStatus:
    """Salva de forma persistente os vídeos de abertura/encerramento (ex:
    o usuário aparecendo em tela cheia). Sobe uma vez, entra
    automaticamente em toda geração depois disso, sem precisar subir de
    novo. Pra camada de webcam/reação, veja /api/text-to-video/webcam-clips
    (é um conjunto de clipes, não um único arquivo)."""
    if intro_video and intro_video.filename:
        save_bumper("intro", intro_video.filename, intro_video.file)
    if outro_video and outro_video.filename:
        save_bumper("outro", outro_video.filename, outro_video.file)
    return _bumpers_status()


@app.delete("/api/text-to-video/bumpers/{which}")
async def delete_bumper(which: str) -> BumperStatus:
    if which not in ("intro", "outro"):
        raise HTTPException(status_code=400, detail="which deve ser 'intro' ou 'outro'")
    remove_bumper(which)
    return _bumpers_status()


@app.post("/api/text-to-video/webcam-clips")
async def upload_webcam_clips(clips: list[UploadFile] = File(...)) -> BumperStatus:
    """Adiciona um ou mais clipes ao POOL de reação/webcam — um é
    sorteado aleatoriamente a cada vídeo gerado, em vez de repetir sempre
    o mesmo clipe curto em loop (visualmente ficava com "saltos" toda
    vez que reiniciava)."""
    for clip in clips:
        if clip.filename:
            add_webcam_clip(clip.filename, clip.file)
    return _bumpers_status()


@app.delete("/api/text-to-video/webcam-clips/{clip_name}")
async def delete_webcam_clip(clip_name: str) -> BumperStatus:
    remove_webcam_clip(clip_name)
    return _bumpers_status()


def _run_text_to_video(
    job_id: str,
    text: str,
    engine: str,
    voice_id: str | None,
    rate: int | None,
    manual_image_map: dict[int, Path] | None,
    subtitles_enabled: bool,
    subtitle_font_size: int | None,
    subtitle_position: str,
    orientation: str,
    cover_image_path: Path | None,
    use_intro: bool,
    use_outro: bool,
    use_webcam: bool,
    webcam_position: str,
) -> None:
    job = TEXT_TO_VIDEO_JOBS[job_id]
    try:
        job.status = "generating"
        job_dir = OUTPUTS_DIR / job_id
        job_dir.mkdir(exist_ok=True)
        output_path = job_dir / "video.mp4"

        api_key = get_pexels_api_key() or ""
        generate_video_from_text(
            text, output_path, api_key, tts_engine=engine, voice_id=voice_id, rate=rate,
            manual_image_map=manual_image_map,
            subtitles_enabled=subtitles_enabled,
            subtitle_font_size=subtitle_font_size,
            subtitle_position=subtitle_position,
            orientation=orientation,
            intro_video_path=get_bumper_path("intro") if use_intro else None,
            outro_video_path=get_bumper_path("outro") if use_outro else None,
            webcam_video_path=get_random_webcam_clip() if use_webcam else None,
            webcam_position=webcam_position,
        )

        thumbnail_path = None
        if cover_image_path:
            thumbnail_path = job_dir / "capa.jpg"
            resolution = VERTICAL_RESOLUTION if orientation == "vertical" else HORIZONTAL_RESOLUTION
            build_cover_thumbnail(cover_image_path, thumbnail_path, resolution=resolution)

        log_path = job_dir / "buscas_de_imagem.log.txt"
        job.result_video = str(output_path)
        job.result_log = str(log_path) if log_path.exists() else None
        job.result_thumbnail = str(thumbnail_path) if thumbnail_path else None
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


@app.post("/api/text-to-video")
async def create_text_to_video(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    engine: str = Form("edge"),
    voice_id: str = Form(""),
    rate: int = Form(0),
    manual_images: list[UploadFile] = File(default=[]),
    chunk_assignments: str = Form(""),
    subtitles_enabled: bool = Form(False),
    subtitle_font_size: int = Form(0),
    subtitle_position: str = Form("bottom"),
    orientation: str = Form("horizontal"),
    cover_image: UploadFile | None = File(None),
    use_intro: bool = Form(True),
    use_outro: bool = Form(True),
    use_webcam: bool = Form(True),
    webcam_position: str = Form("bottom-right"),
) -> TextToVideoJob:
    """`chunk_assignments`: JSON com uma lista do mesmo tamanho dos trechos
    do texto, onde cada item é o índice (dentro de `manual_images`) da
    imagem escolhida manualmente pra aquele trecho, ou `null` pra deixar
    a busca automática decidir. Isso evita depender de uma ordem/ciclo
    fixo das imagens enviadas, que na prática o usuário não controla bem
    (ex: o navegador pode listar os arquivos selecionados fora de ordem).

    `cover_image`: foto opcional escolhida pelo usuário pra ser a capa do
    vídeo (ex: pra usar como thumbnail ao postar em outro lugar) — não
    entra no vídeo em si, só gera um arquivo de imagem separado."""
    job_id = str(uuid.uuid4())

    manual_image_map: dict[int, Path] | None = None
    if manual_images and manual_images[0].filename:
        images_dir = UPLOADS_DIR / job_id / "manual_images"
        images_dir.mkdir(parents=True, exist_ok=True)
        saved_paths: list[Path] = []
        for idx, upload in enumerate(manual_images):
            suffix = Path(upload.filename or "").suffix or ".jpg"
            image_path = images_dir / f"img_{idx:03d}{suffix}"
            with image_path.open("wb") as f:
                shutil.copyfileobj(upload.file, f)
            saved_paths.append(image_path)

        assignments: list[int | None] = json.loads(chunk_assignments) if chunk_assignments else []
        manual_image_map = {
            chunk_index: saved_paths[image_index]
            for chunk_index, image_index in enumerate(assignments)
            if image_index is not None and 0 <= image_index < len(saved_paths)
        }

    cover_image_path: Path | None = None
    if cover_image and cover_image.filename:
        upload_dir = UPLOADS_DIR / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(cover_image.filename).suffix or ".jpg"
        cover_image_path = upload_dir / f"capa_original{suffix}"
        with cover_image_path.open("wb") as f:
            shutil.copyfileobj(cover_image.file, f)

    job = TextToVideoJob(id=job_id)
    TEXT_TO_VIDEO_JOBS[job_id] = job
    background_tasks.add_task(
        _run_text_to_video, job_id, text, engine, voice_id.strip() or None, rate or None, manual_image_map,
        subtitles_enabled, subtitle_font_size or None, subtitle_position, orientation, cover_image_path,
        use_intro, use_outro, use_webcam, webcam_position,
    )
    return job


@app.get("/api/text-to-video/{job_id}")
async def get_text_to_video(job_id: str) -> TextToVideoJob:
    return TEXT_TO_VIDEO_JOBS[job_id]


@app.get("/api/text-to-video/{job_id}/thumbnail")
async def download_text_to_video_thumbnail(job_id: str) -> FileResponse:
    job = TEXT_TO_VIDEO_JOBS[job_id]
    return FileResponse(job.result_thumbnail, filename="capa.jpg")


@app.get("/api/text-to-video/{job_id}/video")
async def download_text_to_video(job_id: str) -> FileResponse:
    job = TEXT_TO_VIDEO_JOBS[job_id]
    return FileResponse(job.result_video, filename="video.mp4")


@app.get("/api/text-to-video/{job_id}/log")
async def download_text_to_video_log(job_id: str) -> FileResponse:
    job = TEXT_TO_VIDEO_JOBS[job_id]
    return FileResponse(job.result_log, filename="buscas_de_imagem.log.txt")


# --- Frontend ---------------------------------------------------------------
# Serve o app React já compilado (frontend-app/ -> backend/static/), assim o
# usuário abre uma única URL (http://localhost:8000) em vez de arquivos HTML
# soltos. Precisa ser o ÚLTIMO registro de rota: qualquer caminho que não
# bata com uma rota /api/* definida acima cai aqui.
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
