"""API local do editor de vídeo automático. Nenhuma chamada externa é feita:
todo o processamento (corte de silêncio, transcrição, legendas) roda na
própria máquina."""
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.background_removal import remove_background
from pipeline.enhance import enhance
from pipeline.ffprobe_utils import probe_duration
from pipeline.filler_removal import remove_fillers
from pipeline.reframe import reframe_vertical
from pipeline.silence_cut import cut_silence
from pipeline.stabilize import stabilize
from pipeline.subtitles import burn_subtitles, write_srt
from pipeline.timeline_render import render_edl
from pipeline.transcribe import transcribe
from pipeline.tts import synthesize_speech
from pipeline.upscale import upscale

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
            remove_background(
                current_video, bg_video, job_dir / "bg_tmp", background_color=background_color or None
            )
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
            write_srt(segments, srt_path)

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

TranscriptionStatus = Literal["queued", "transcribing", "done", "error"]


class TranscriptionJob(BaseModel):
    id: str
    status: TranscriptionStatus = "queued"
    error: str | None = None
    result_txt: str | None = None
    result_srt: str | None = None


TRANSCRIPTION_JOBS: dict[str, TranscriptionJob] = {}


def _run_transcription(job_id: str, input_path: Path) -> None:
    job = TRANSCRIPTION_JOBS[job_id]
    try:
        job.status = "transcribing"
        segments = transcribe(input_path)

        job_dir = OUTPUTS_DIR / job_id
        job_dir.mkdir(exist_ok=True)

        txt_path = job_dir / "transcricao.txt"
        txt_path.write_text("\n".join(s.text for s in segments), encoding="utf-8")

        srt_path = job_dir / "transcricao.srt"
        write_srt(segments, srt_path)

        job.result_txt = str(txt_path)
        job.result_srt = str(srt_path)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


@app.post("/api/transcriptions")
async def create_transcription(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> TranscriptionJob:
    job_id = str(uuid.uuid4())
    upload_dir = UPLOADS_DIR / job_id
    upload_dir.mkdir(parents=True)

    input_path = upload_dir / "input.mp4"
    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    job = TranscriptionJob(id=job_id)
    TRANSCRIPTION_JOBS[job_id] = job
    background_tasks.add_task(_run_transcription, job_id, input_path)
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


def _run_tts(job_id: str, text: str, rate: int | None) -> None:
    job = TTS_JOBS[job_id]
    try:
        job.status = "generating"
        job_dir = OUTPUTS_DIR / job_id
        job_dir.mkdir(exist_ok=True)
        output_path = job_dir / "voz.wav"

        synthesize_speech(text, output_path, rate=rate)

        job.result_audio = str(output_path)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


@app.post("/api/tts")
async def create_tts(background_tasks: BackgroundTasks, text: str = Form(...), rate: int = Form(0)) -> TtsJob:
    job_id = str(uuid.uuid4())
    job = TtsJob(id=job_id)
    TTS_JOBS[job_id] = job
    background_tasks.add_task(_run_tts, job_id, text, rate or None)
    return job


@app.get("/api/tts/{job_id}")
async def get_tts(job_id: str) -> TtsJob:
    return TTS_JOBS[job_id]


@app.get("/api/tts/{job_id}/audio")
async def download_tts(job_id: str) -> FileResponse:
    job = TTS_JOBS[job_id]
    return FileResponse(job.result_audio, filename="voz.wav")
