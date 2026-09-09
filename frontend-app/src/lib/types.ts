export type JobStatus =
  | "queued"
  | "cutting_silence"
  | "removing_fillers"
  | "stabilizing"
  | "enhancing"
  | "removing_background"
  | "reframing_vertical"
  | "upscaling"
  | "transcribing"
  | "generating_subtitles"
  | "done"
  | "error";

export interface Job {
  id: string;
  status: JobStatus;
  error: string | null;
  result_video: string | null;
  result_srt: string | null;
}

export interface AutoEditOptions {
  cut_silence_enabled: boolean;
  remove_fillers_enabled: boolean;
  stabilize_enabled: boolean;
  enhance_enabled: boolean;
  reframe_enabled: boolean;
  remove_bg_enabled: boolean;
  background_color: string;
  upscale_enabled: boolean;
  subtitles_enabled: boolean;
  burn_in: boolean;
  subtitle_font_size: number;
  subtitle_position: "bottom" | "middle" | "top";
}

export interface UploadInfo {
  upload_id: string;
  duration: number;
}

export interface EdlSegment {
  start: number;
  end: number;
  speed: number;
  volume: number;
  color_filter: "none" | "vibrant" | "bw" | "warm" | "cool";
}

export interface TextOverlay {
  text: string;
  start: number;
  end: number;
  x_percent: number;
  y_percent: number;
  font_size: number;
  color: string;
}

export type RenderStatus = "queued" | "rendering" | "done" | "error";

export interface RenderJob {
  id: string;
  status: RenderStatus;
  error: string | null;
  result_video: string | null;
}

export type TranscriptionStatus = "queued" | "transcribing" | "done" | "error";

export interface TranscriptionJob {
  id: string;
  status: TranscriptionStatus;
  error: string | null;
  result_txt: string | null;
  result_srt: string | null;
}

export type TtsStatus = "queued" | "generating" | "done" | "error";

export interface TtsJob {
  id: string;
  status: TtsStatus;
  error: string | null;
  result_audio: string | null;
}
