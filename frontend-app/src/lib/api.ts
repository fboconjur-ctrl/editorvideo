import type {
  AutoEditOptions,
  Job,
  RenderJob,
  TranscriptionJob,
  TtsJob,
  UploadInfo,
  EdlSegment,
  TextOverlay,
  VoiceOption,
  TtsEngine,
  TextToVideoJob,
  SettingsInfo,
} from "./types";

// Em produção o app é servido pelo próprio FastAPI (mesma origem), então a
// base pode ser relativa. Em desenvolvimento (`npm run dev`) o vite.config.ts
// faz proxy de /api para localhost:8000.
const API_BASE = "";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    throw new ApiError(
      "Não foi possível conectar ao servidor. Verifique se a janela do setup_e_rodar.bat ainda está aberta e rodando."
    );
  }
  if (!res.ok) {
    throw new ApiError(`Falha na requisição (HTTP ${res.status}).`);
  }
  return res.json();
}

export function createAutoJob(file: File, options: AutoEditOptions): Promise<Job> {
  const formData = new FormData();
  formData.append("file", file);
  for (const [key, value] of Object.entries(options)) {
    formData.append(key, String(value));
  }
  return request<Job>("/api/jobs", { method: "POST", body: formData });
}

export function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}`);
}

export function jobVideoUrl(jobId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/video`;
}

export function jobSubtitlesUrl(jobId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/subtitles`;
}

export function promoteJob(jobId: string): Promise<UploadInfo> {
  return request<UploadInfo>(`/api/jobs/${jobId}/promote`, { method: "POST" });
}

export function createUpload(file: File): Promise<UploadInfo> {
  const formData = new FormData();
  formData.append("file", file);
  return request<UploadInfo>("/api/uploads", { method: "POST", body: formData });
}

export function uploadVideoUrl(uploadId: string): string {
  return `${API_BASE}/api/uploads/${uploadId}/video`;
}

export function createRender(
  uploadId: string,
  segments: EdlSegment[],
  texts: TextOverlay[]
): Promise<RenderJob> {
  return request<RenderJob>("/api/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: uploadId, segments, texts }),
  });
}

export function getRender(jobId: string): Promise<RenderJob> {
  return request<RenderJob>(`/api/render/${jobId}`);
}

export function renderVideoUrl(jobId: string): string {
  return `${API_BASE}/api/render/${jobId}/video`;
}

export function createTranscription(
  file: File | null,
  youtubeUrl?: string,
  diarize?: boolean
): Promise<TranscriptionJob> {
  const formData = new FormData();
  if (file) formData.append("file", file);
  if (youtubeUrl) formData.append("youtube_url", youtubeUrl);
  formData.append("diarize", String(!!diarize));
  return request<TranscriptionJob>("/api/transcriptions", { method: "POST", body: formData });
}

export function getTranscription(jobId: string): Promise<TranscriptionJob> {
  return request<TranscriptionJob>(`/api/transcriptions/${jobId}`);
}

export function transcriptionTxtUrl(jobId: string): string {
  return `${API_BASE}/api/transcriptions/${jobId}/txt`;
}

export function transcriptionSrtUrl(jobId: string): string {
  return `${API_BASE}/api/transcriptions/${jobId}/srt`;
}

export function createTts(text: string, engine: TtsEngine, rate: number, voiceId?: string): Promise<TtsJob> {
  const formData = new FormData();
  formData.append("text", text);
  formData.append("engine", engine);
  formData.append("rate", String(rate));
  if (voiceId) formData.append("voice_id", voiceId);
  return request<TtsJob>("/api/tts", { method: "POST", body: formData });
}

export function getVoices(engine: TtsEngine): Promise<VoiceOption[]> {
  return request<VoiceOption[]>(`/api/tts/voices?engine=${engine}`);
}

export function getTts(jobId: string): Promise<TtsJob> {
  return request<TtsJob>(`/api/tts/${jobId}`);
}

export function ttsAudioUrl(jobId: string): string {
  return `${API_BASE}/api/tts/${jobId}/audio`;
}

export function getSettings(): Promise<SettingsInfo> {
  return request<SettingsInfo>("/api/settings");
}

export function saveSettings(settings: { pexelsApiKey?: string; huggingfaceToken?: string }): Promise<SettingsInfo> {
  return request<SettingsInfo>("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pexels_api_key: settings.pexelsApiKey,
      huggingface_token: settings.huggingfaceToken,
    }),
  });
}

export function previewTextToVideoChunks(text: string): Promise<string[]> {
  const formData = new FormData();
  formData.append("text", text);
  return request<string[]>("/api/text-to-video/chunks", { method: "POST", body: formData });
}

export interface ChunkMediaOption {
  index: number;
  type: "photo" | "video" | string;
  source: string;
  url: string;
}

export interface ChunkMediaOptions {
  text: string;
  options: ChunkMediaOption[];
}

export interface ChunkMediaPreview {
  chunks: ChunkMediaOptions[];
}

export function previewChunkMediaOptions(
  text: string,
  orientation: "horizontal" | "vertical",
  preferPhotos: boolean
): Promise<ChunkMediaPreview> {
  const formData = new FormData();
  formData.append("text", text);
  formData.append("orientation", orientation);
  formData.append("prefer_photos", String(preferPhotos));
  return request<ChunkMediaPreview>("/api/text-to-video/chunk-media-options", { method: "POST", body: formData });
}

export function createTextToVideo(
  text: string,
  engine: TtsEngine,
  rate: number,
  voiceId?: string,
  manualImages?: File[],
  chunkAssignments?: (number | null)[],
  subtitlesEnabled?: boolean,
  orientation?: "horizontal" | "vertical",
  coverImage?: File | null,
  useIntro?: boolean,
  useOutro?: boolean,
  useWebcam?: boolean,
  webcamPosition?: WebcamPosition,
  subtitleStyle?: "static" | "karaoke",
  preferPhotos?: boolean
): Promise<TextToVideoJob> {
  const formData = new FormData();
  formData.append("text", text);
  formData.append("engine", engine);
  formData.append("rate", String(rate));
  if (voiceId) formData.append("voice_id", voiceId);
  for (const image of manualImages ?? []) {
    formData.append("manual_images", image);
  }
  if (chunkAssignments) {
    formData.append("chunk_assignments", JSON.stringify(chunkAssignments));
  }
  if (subtitlesEnabled) {
    formData.append("subtitles_enabled", "true");
  }
  formData.append("subtitle_style", subtitleStyle ?? "static");
  formData.append("orientation", orientation ?? "horizontal");
  if (coverImage) {
    formData.append("cover_image", coverImage);
  }
  formData.append("use_intro", String(useIntro ?? true));
  formData.append("use_outro", String(useOutro ?? true));
  formData.append("use_webcam", String(useWebcam ?? true));
  formData.append("webcam_position", webcamPosition ?? "bottom-right");
  formData.append("prefer_photos", String(preferPhotos ?? true));
  return request<TextToVideoJob>("/api/text-to-video", { method: "POST", body: formData });
}

export function textToVideoThumbnailUrl(jobId: string): string {
  return `${API_BASE}/api/text-to-video/${jobId}/thumbnail`;
}

export type WebcamPosition = "bottom-right" | "bottom-left" | "top-right" | "top-left";

export interface BumperStatus {
  has_intro: boolean;
  has_outro: boolean;
  webcam_clips: string[];
}

export function getBumpersStatus(): Promise<BumperStatus> {
  return request<BumperStatus>("/api/text-to-video/bumpers");
}

export function uploadBumpers(introVideo?: File | null, outroVideo?: File | null): Promise<BumperStatus> {
  const formData = new FormData();
  if (introVideo) formData.append("intro_video", introVideo);
  if (outroVideo) formData.append("outro_video", outroVideo);
  return request<BumperStatus>("/api/text-to-video/bumpers", { method: "POST", body: formData });
}

export function deleteBumper(which: "intro" | "outro"): Promise<BumperStatus> {
  return request<BumperStatus>(`/api/text-to-video/bumpers/${which}`, { method: "DELETE" });
}

export function uploadWebcamClips(clips: File[]): Promise<BumperStatus> {
  const formData = new FormData();
  for (const clip of clips) {
    formData.append("clips", clip);
  }
  return request<BumperStatus>("/api/text-to-video/webcam-clips", { method: "POST", body: formData });
}

export function deleteWebcamClip(clipName: string): Promise<BumperStatus> {
  return request<BumperStatus>(`/api/text-to-video/webcam-clips/${encodeURIComponent(clipName)}`, {
    method: "DELETE",
  });
}

export function getTextToVideo(jobId: string): Promise<TextToVideoJob> {
  return request<TextToVideoJob>(`/api/text-to-video/${jobId}`);
}

export function textToVideoUrl(jobId: string): string {
  return `${API_BASE}/api/text-to-video/${jobId}/video`;
}

export function textToVideoLogUrl(jobId: string): string {
  return `${API_BASE}/api/text-to-video/${jobId}/log`;
}
