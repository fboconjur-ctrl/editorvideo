import { useState } from "react";
import { Download, Mic, Volume2 } from "lucide-react";
import { Card, CardTitle, CardSubtitle } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Dropzone } from "../components/ui/Dropzone";
import * as api from "../lib/api";

export function ToolsPage() {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <TranscriptionCard />
      <TtsCard />
    </div>
  );
}

function TranscriptionCard() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ jobId: string } | null>(null);

  async function handleTranscribe() {
    if (!file) return;
    setBusy(true);
    setResult(null);
    setStatus("Enviando arquivo...");
    try {
      const job = await api.createTranscription(file);
      await poll(job.id);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

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
      setStatus("Transcrevendo áudio (pode demorar um pouco)...");
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  return (
    <Card>
      <div className="flex items-center gap-2">
        <Mic className="h-4 w-4 text-accent" />
        <CardTitle>Transcrever vídeo/áudio</CardTitle>
      </div>
      <CardSubtitle>Sobe um arquivo e recebe de volta o texto e a legenda (.srt).</CardSubtitle>

      <div className="mt-4">
        <Dropzone onFile={setFile} fileName={file?.name} />
      </div>

      <Button className="mt-4" onClick={handleTranscribe} disabled={!file || busy}>
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
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  async function handleGenerate() {
    if (!text.trim()) return;
    setBusy(true);
    setAudioUrl(null);
    setStatus("Gerando áudio...");
    try {
      const job = await api.createTts(text, Number(rate) || 0);
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

      <div className="mt-3">
        <label className="text-xs text-slate-400">Velocidade da fala (deixe em branco para o padrão)</label>
        <input
          className="input-field mt-1"
          placeholder="ex: 150 (palavras por minuto)"
          value={rate}
          onChange={(e) => setRate(e.target.value)}
        />
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
