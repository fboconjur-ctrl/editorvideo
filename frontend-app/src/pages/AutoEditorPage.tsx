import { useEffect, useRef, useState } from "react";
import { Wand2, Download, Scissors } from "lucide-react";
import { Card, CardTitle, CardSubtitle } from "../components/ui/Card";
import { Toggle } from "../components/ui/Toggle";
import { Button } from "../components/ui/Button";
import { Dropzone } from "../components/ui/Dropzone";
import { VideoCanvas } from "../components/VideoCanvas";
import { ProgressSteps, StepDef, StepState } from "../components/ui/ProgressSteps";
import * as api from "../lib/api";
import type { AutoEditOptions, Job, JobStatus } from "../lib/types";

const STEP_DEFS: (StepDef & { optionKey?: keyof AutoEditOptions })[] = [
  { key: "uploading", label: "Enviar vídeo" },
  { key: "cutting_silence", label: "Cortar silêncios/pausas", optionKey: "cut_silence_enabled" },
  { key: "removing_fillers", label: "Remover palavras repetidas/vícios de fala", optionKey: "remove_fillers_enabled" },
  { key: "stabilizing", label: "Estabilizar imagem", optionKey: "stabilize_enabled" },
  { key: "enhancing", label: "Corrigir cor e áudio", optionKey: "enhance_enabled" },
  { key: "reframing_vertical", label: "Reframe vertical", optionKey: "reframe_enabled" },
  { key: "removing_background", label: "Remover fundo", optionKey: "remove_bg_enabled" },
  { key: "upscaling", label: "Aumentar resolução", optionKey: "upscale_enabled" },
  { key: "transcribing", label: "Transcrever áudio", optionKey: "subtitles_enabled" },
  { key: "generating_subtitles", label: "Gerar legendas", optionKey: "subtitles_enabled" },
  { key: "done", label: "Concluído" },
];

const DEFAULT_OPTIONS: AutoEditOptions = {
  cut_silence_enabled: true,
  remove_fillers_enabled: false,
  stabilize_enabled: false,
  enhance_enabled: true,
  reframe_enabled: false,
  remove_bg_enabled: false,
  background_color: "",
  upscale_enabled: false,
  subtitles_enabled: true,
  burn_in: true,
  subtitle_font_size: 0,
  subtitle_position: "bottom",
};

export function AutoEditorPage({ onEditManually }: { onEditManually: (uploadId: string, duration: number) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [options, setOptions] = useState<AutoEditOptions>(DEFAULT_OPTIONS);
  const [processing, setProcessing] = useState(false);
  const [activeSteps, setActiveSteps] = useState<StepDef[]>([]);
  const [stepStates, setStepStates] = useState<Record<string, StepState>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [promoting, setPromoting] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoBox, setVideoBox] = useState({ width: 0, height: 0, videoHeight: 0 });

  function set<K extends keyof AutoEditOptions>(key: K, value: AutoEditOptions[K]) {
    setOptions((prev) => ({ ...prev, [key]: value }));
  }

  function handleFile(f: File) {
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
    setJob(null);
    setErrorMessage(null);
  }

  function updateVideoBox() {
    const v = videoRef.current;
    if (!v) return;
    setVideoBox({ width: v.clientWidth, height: v.clientHeight, videoHeight: v.videoHeight });
  }

  useEffect(() => {
    window.addEventListener("resize", updateVideoBox);
    return () => window.removeEventListener("resize", updateVideoBox);
  }, []);

  const relevantSteps = STEP_DEFS.filter((s) => !s.optionKey || options[s.optionKey]);

  async function handleProcess() {
    if (!file) return;
    setProcessing(true);
    setErrorMessage(null);
    setJob(null);
    setActiveSteps(relevantSteps);
    setStepStates({ uploading: "active" });

    try {
      const createdJob = await api.createAutoJob(file, options);
      await pollJob(createdJob.id, relevantSteps);
    } catch (err) {
      setStepStates((prev) => ({ ...prev, uploading: "error" }));
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setProcessing(false);
    }
  }

  async function pollJob(jobId: string, steps: StepDef[]) {
    let lastStatus: JobStatus | "uploading" = "uploading";

    // eslint-disable-next-line no-constant-condition
    while (true) {
      let current: Job;
      try {
        current = await api.getJob(jobId);
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : String(err));
        setProcessing(false);
        return;
      }

      if (current.status === "error") {
        const order = steps.map((s) => s.key);
        const lastIndex = order.indexOf(lastStatus);
        const newStates: Record<string, StepState> = {};
        order.forEach((key, i) => {
          if (i < lastIndex) newStates[key] = "done";
        });
        setStepStates(newStates);
        const lastLabel = steps.find((s) => s.key === lastStatus)?.label ?? lastStatus;
        setErrorMessage(`Falha depois da etapa "${lastLabel}". ${current.error}`);
        setProcessing(false);
        return;
      }

      if (current.status === "done") {
        const newStates: Record<string, StepState> = {};
        steps.forEach((s) => (newStates[s.key] = "done"));
        setStepStates(newStates);
        setJob(current);
        setProcessing(false);
        return;
      }

      lastStatus = current.status;
      const order = steps.map((s) => s.key);
      const currentIndex = order.indexOf(current.status);
      const newStates: Record<string, StepState> = {};
      order.forEach((key, i) => {
        if (i < currentIndex) newStates[key] = "done";
        else if (i === currentIndex) newStates[key] = "active";
      });
      setStepStates(newStates);

      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function handleEditManually() {
    if (!job) return;
    setPromoting(true);
    try {
      const info = await api.promoteJob(job.id);
      onEditManually(info.upload_id, info.duration);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setPromoting(false);
    }
  }

  const showSubtitlePreview = options.subtitles_enabled && options.burn_in && videoBox.videoHeight > 0;
  const subtitleFontPx = showSubtitlePreview
    ? Math.min(
        Math.max(8, (options.subtitle_font_size || Math.round(videoBox.videoHeight / 22)) * (videoBox.height / videoBox.videoHeight)),
        videoBox.height * 0.2
      )
    : 0;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Card>
        <CardTitle>Vídeo</CardTitle>
        <CardSubtitle>Suba o vídeo e veja a prévia antes de processar.</CardSubtitle>
        <div className="mt-4">
          <Dropzone onFile={handleFile} fileName={file?.name} />
        </div>

        {previewUrl && (
          <div className="mt-5">
            <VideoCanvas
              videoRef={videoRef}
              src={job ? api.jobVideoUrl(job.id) : previewUrl}
              onLoadedMetadata={updateVideoBox}
            >
              {showSubtitlePreview && !job && (
                <div
                  className="absolute left-[4%] right-[4%] text-center font-semibold text-white"
                  style={{
                    fontSize: `${subtitleFontPx}px`,
                    top: options.subtitle_position === "top" ? "6%" : options.subtitle_position === "middle" ? "45%" : undefined,
                    bottom: options.subtitle_position === "bottom" ? "6%" : undefined,
                    textShadow: "0 0 3px #000, 0 0 6px #000, 1px 1px 1px #000",
                  }}
                >
                  Assim vai ficar a legenda
                </div>
              )}
            </VideoCanvas>
          </div>
        )}

        {(processing || Object.keys(stepStates).length > 0) && (
          <div className="mt-5 rounded-xl border border-base-700 bg-base-900 p-4">
            <ProgressSteps steps={activeSteps} states={stepStates} />
            {errorMessage && <p className="mt-3 text-sm text-red-400">{errorMessage}</p>}
          </div>
        )}

        {job?.status === "done" && (
          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => window.open(api.jobVideoUrl(job.id), "_blank")}>
              <Download className="h-4 w-4" /> Baixar vídeo
            </Button>
            {job.result_srt && (
              <Button variant="secondary" onClick={() => window.open(api.jobSubtitlesUrl(job.id), "_blank")}>
                <Download className="h-4 w-4" /> Baixar legendas
              </Button>
            )}
            <Button variant="secondary" onClick={handleEditManually} disabled={promoting}>
              <Scissors className="h-4 w-4" /> {promoting ? "Preparando..." : "Editar manualmente este resultado"}
            </Button>
          </div>
        )}
      </Card>

      <Card className="flex flex-col">
        <CardTitle>Automações</CardTitle>
        <CardSubtitle>Marque o que quiser aplicar automaticamente.</CardSubtitle>

        <div className="mt-2 divide-y divide-base-700/60">
          <Toggle checked={options.cut_silence_enabled} onChange={(v) => set("cut_silence_enabled", v)} label="Cortar silêncios/pausas" />
          <Toggle
            checked={options.remove_fillers_enabled}
            onChange={(v) => set("remove_fillers_enabled", v)}
            label="Remover palavras repetidas / vícios de fala"
            description="né, tipo, uhm..."
          />
          <Toggle checked={options.stabilize_enabled} onChange={(v) => set("stabilize_enabled", v)} label="Estabilizar imagem tremida" />
          <Toggle checked={options.enhance_enabled} onChange={(v) => set("enhance_enabled", v)} label="Corrigir cor e normalizar áudio" />
          <Toggle checked={options.reframe_enabled} onChange={(v) => set("reframe_enabled", v)} label="Reframe vertical (9:16, segue o rosto)" />
          <Toggle checked={options.remove_bg_enabled} onChange={(v) => set("remove_bg_enabled", v)} label="Remover fundo" />
          {options.remove_bg_enabled && (
            <div className="py-2.5 pl-2">
              <label className="text-xs text-slate-400">Fundo sólido (vazio = transparente)</label>
              <input
                className="input-field mt-1"
                placeholder="ex: green, #00ff00"
                value={options.background_color}
                onChange={(e) => set("background_color", e.target.value)}
              />
            </div>
          )}
          <Toggle checked={options.upscale_enabled} onChange={(v) => set("upscale_enabled", v)} label="Aumentar resolução (2x, nitidez)" />
          <Toggle checked={options.subtitles_enabled} onChange={(v) => set("subtitles_enabled", v)} label="Gerar legendas automáticas" />
          {options.subtitles_enabled && (
            <>
              <Toggle checked={options.burn_in} onChange={(v) => set("burn_in", v)} label="Queimar legendas no vídeo" />
              {options.burn_in && (
                <div className="grid grid-cols-2 gap-3 py-2.5 pl-2">
                  <div>
                    <label className="text-xs text-slate-400">Tamanho da fonte</label>
                    <input
                      type="number"
                      className="input-field mt-1"
                      placeholder="auto"
                      value={options.subtitle_font_size || ""}
                      onChange={(e) => set("subtitle_font_size", Number(e.target.value) || 0)}
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400">Posição</label>
                    <select
                      className="input-field mt-1"
                      value={options.subtitle_position}
                      onChange={(e) => set("subtitle_position", e.target.value as AutoEditOptions["subtitle_position"])}
                    >
                      <option value="bottom">Embaixo</option>
                      <option value="middle">Meio</option>
                      <option value="top">Em cima</option>
                    </select>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <Button className="mt-5 w-full justify-center" onClick={handleProcess} disabled={!file || processing}>
          <Wand2 className="h-4 w-4" /> {processing ? "Processando..." : "Processar vídeo"}
        </Button>
      </Card>
    </div>
  );
}
