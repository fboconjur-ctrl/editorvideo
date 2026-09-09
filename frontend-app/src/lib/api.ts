import type {
  AutoEditOptions,
  Job,
  RenderJob,
  TranscriptionJob,
  TtsJob,
  UploadInfo,
  EdlSegment,
  TextOverlay,
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

export function createTranscription(file: File): Promise<TranscriptionJob> {
  const formData = new FormData();
  formData.append("file", file);
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

export function createTts(text: string, rate: number): Promise<TtsJob> {
  const formData = new FormData();
  formData.append("text", text);
  formData.append("rate", String(rate));
  return request<TtsJob>("/api/tts", { method: "POST", body: formData });
}

export function getTts(jobId: string): Promise<TtsJob> {
  return request<TtsJob>(`/api/tts/${jobId}`);
}

export function ttsAudioUrl(jobId: string): string {
  return `${API_BASE}/api/tts/${jobId}/audio`;
}
