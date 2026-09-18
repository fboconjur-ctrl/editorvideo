import { useEffect, useState } from "react";
import { Download, Mic, Volume2, Link as LinkIcon, Upload } from "lucide-react";
import { Card, CardTitle, CardSubtitle } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Dropzone } from "../components/ui/Dropzone";
import * as api from "../lib/api";
import type { VoiceOption } from "../lib/types";

export function ToolsPage() {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <TranscriptionCard />
      <TtsCard />
    </div>
  );
}

function TranscriptionCard() {
  const [source, setSource] = useState<"upload" | "youtube">("upload");
  const [file, setFile] = useState<File | null>(null);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ jobId: string } | null>(null);

  const canSubmit = source === "upload" ? !!file : youtubeUrl.trim().length > 0;

  async function handleTranscribe() {
    if (!canSubmit) return;
    setBusy(true);
    setResult(null);
    setStatus(source === "youtube" ? "Baixando áudio do YouTube..." : "Enviando arquivo...");
    try {
      const job = await api.createTranscription(source === "upload" ? file : null, source === "youtube" ? youtubeUrl.trim() : undefined);
      await poll(job.id);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  const STATUS_LABELS: Record<string, string> = {
    downloading: "Baixando áudio do YouTube...",
    transcribing: "Transcrevendo áudio (pode demorar um pouco)...",
  };

  async function poll(jobId: string) {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const job = await api.getTranscription(jobId);
      if (job.status === "done") {
        setStatus("Transcrição concluída!");
        setResult({ jobId });
        setBusy(false);
        return;
      }
      if (job.status === "error") {
        setStatus(`Erro: ${job.error}`);
        setBusy(false);
        return;
      }
      setStatus(STATUS_LABELS[job.status] ?? job.status);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  return (
    <Card>
      <div className="flex items-center gap-2">
        <Mic className="h-4 w-4 text-accent" />
        <CardTitle>Transcrever vídeo/áudio</CardTitle>
      </div>
      <CardSubtitle>Sobe um arquivo ou cola um link do YouTube — recebe de volta o texto e a legenda (.srt).</CardSubtitle>

      <div className="mt-4 flex gap-1 rounded-lg border border-base-700 bg-base-900 p-1">
        <button
          onClick={() => setSource("upload")}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-medium ${
            source === "upload" ? "bg-accent text-white" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Upload className="h-3.5 w-3.5" /> Arquivo
        </button>
        <button
          onClick={() => setSource("youtube")}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-medium ${
            source === "youtube" ? "bg-accent text-white" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <LinkIcon className="h-3.5 w-3.5" /> Link do YouTube
        </button>
      </div>

      <div className="mt-4">
        {source === "upload" ? (
          <Dropzone onFile={setFile} fileName={file?.name} />
        ) : (
          <input
            className="input-field"
            placeholder="https://www.youtube.com/watch?v=..."
            value={youtubeUrl}
            onChange={(e) => setYoutubeUrl(e.target.value)}
          />
        )}
      </div>

      <Button className="mt-4" onClick={handleTranscribe} disabled={!canSubmit || busy}>
        {busy ? "Transcrevendo..." : "Transcrever"}
      </Button>

      {status && <p className="mt-3 text-sm text-slate-400">{status}</p>}

      {result && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => window.open(api.transcriptionTxtUrl(result.jobId), "_blank")}>
            <Download className="h-4 w-4" /> Baixar texto
          </Button>
          <Button variant="secondary" onClick={() => window.open(api.transcriptionSrtUrl(result.jobId), "_blank")}>
            <Download className="h-4 w-4" /> Baixar legenda
          </Button>
        </div>
      )}
    </Card>
  );
}

function TtsCard() {
  const [text, setText] = useState("");
  const [rate, setRate] = useState("");
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [voiceId, setVoiceId] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  useEffect(() => {
    api
      .getVoices()
      .then(setVoices)
      .catch(() => setVoices([]));
  }, []);

  async function handleGenerate() {
    if (!text.trim()) return;
    setBusy(true);
    setAudioUrl(null);
    setStatus("Gerando áudio...");
    try {
      const job = await api.createTts(text, Number(rate) || 0, voiceId || undefined);
      await poll(job.id);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  async function poll(jobId: string) {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const job = await api.getTts(jobId);
      if (job.status === "done") {
        setStatus("Áudio gerado!");
        setAudioUrl(api.ttsAudioUrl(jobId));
        setBusy(false);
        return;
      }
      if (job.status === "error") {
        setStatus(`Erro: ${job.error}`);
        setBusy(false);
        return;
      }
      await new Promise((r) => setTimeout(r, 1200));
    }
  }

  return (
    <Card>
      <div className="flex items-center gap-2">
        <Volume2 className="h-4 w-4 text-accent" />
        <CardTitle>Texto para voz</CardTitle>
      </div>
      <CardSubtitle>Gera um áudio narrado usando as vozes já instaladas no seu sistema.</CardSubtitle>

      <textarea
        className="input-field mt-4 min-h-[120px] resize-y"
        placeholder="Digite o texto que vai virar narração..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-400">Voz</label>
          <select className="input-field mt-1" value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
            <option value="">Padrão do sistema</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} {v.languages.length ? `(${v.languages.join(", ")})` : ""}
              </option>
            ))}
          </select>
          {voices.length === 0 && (
            <p className="mt-1 text-xs text-slate-500">
              Nenhuma voz extra detectada. No Windows: Configurações → Hora e idioma → Fala → Adicionar vozes.
            </p>
          )}
        </div>
        <div>
          <label className="text-xs text-slate-400">Velocidade (em branco = padrão)</label>
          <input
            className="input-field mt-1"
            placeholder="ex: 150"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
          />
        </div>
      </div>

      <Button className="mt-4" onClick={handleGenerate} disabled={!text.trim() || busy}>
        {busy ? "Gerando..." : "Gerar áudio"}
      </Button>

      {status && <p className="mt-3 text-sm text-slate-400">{status}</p>}

      {audioUrl && (
        <div className="mt-3 space-y-2">
          <audio src={audioUrl} controls className="w-full" />
          <Button variant="secondary" onClick={() => window.open(audioUrl, "_blank")}>
            <Download className="h-4 w-4" /> Baixar áudio
          </Button>
        </div>
      )}
    </Card>
  );
}
