import { useEffect, useState } from "react";
import { Download, Mic, Volume2, Link as LinkIcon, Upload, Clapperboard, KeyRound } from "lucide-react";
import { Card, CardTitle, CardSubtitle } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Toggle } from "../components/ui/Toggle";
import { Dropzone } from "../components/ui/Dropzone";
import * as api from "../lib/api";
import type { TtsEngine, VoiceOption } from "../lib/types";

export function ToolsPage() {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <TranscriptionCard />
      <TtsCard />
      <TextToVideoCard />
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

  const [diarize, setDiarize] = useState(false);
  const [hasHfToken, setHasHfToken] = useState<boolean | null>(null);
  const [hfTokenInput, setHfTokenInput] = useState("");
  const [savingToken, setSavingToken] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => setHasHfToken(s.has_huggingface_token))
      .catch(() => setHasHfToken(false));
  }, []);

  async function handleSaveToken() {
    if (!hfTokenInput.trim()) return;
    setSavingToken(true);
    try {
      const s = await api.saveSettings({ huggingfaceToken: hfTokenInput.trim() });
      setHasHfToken(s.has_huggingface_token);
      setHfTokenInput("");
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingToken(false);
    }
  }

  const canSubmit = source === "upload" ? !!file : youtubeUrl.trim().length > 0;

  async function handleTranscribe() {
    if (!canSubmit) return;
    setBusy(true);
    setResult(null);
    setStatus(source === "youtube" ? "Baixando áudio do YouTube..." : "Enviando arquivo...");
    try {
      const job = await api.createTranscription(
        source === "upload" ? file : null,
        source === "youtube" ? youtubeUrl.trim() : undefined,
        diarize
      );
      await poll(job.id);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  const STATUS_LABELS: Record<string, string> = {
    downloading: "Baixando áudio do YouTube...",
    transcribing: "Transcrevendo áudio (pode demorar um pouco)...",
    identifying_speakers: "Identificando quem está falando...",
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

      <div className="mt-2">
        <Toggle
          checked={diarize}
          onChange={setDiarize}
          label="Separar por quem fala"
          description="Identifica cada pessoa na conversa (ex: [Pessoa 1], [Pessoa 2])"
        />
      </div>

      {diarize && hasHfToken === false && (
        <div className="mt-2 rounded-lg border border-amber-700/40 bg-amber-500/10 p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-300">
            <KeyRound className="h-4 w-4" /> Token do Hugging Face necessário
          </div>
          <p className="mt-1 text-xs text-amber-200/80">
            Grátis — crie uma conta em{" "}
            <a href="https://huggingface.co/join" target="_blank" rel="noreferrer" className="underline">
              huggingface.co
            </a>
            , aceite os termos do modelo em{" "}
            <a
              href="https://huggingface.co/pyannote/speaker-diarization-3.1"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              pyannote/speaker-diarization-3.1
            </a>{" "}
            e gere um token em{" "}
            <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noreferrer" className="underline">
              settings/tokens
            </a>
            . Fica salvo localmente, não precisa colar de novo.
          </p>
          <div className="mt-2 flex gap-2">
            <input
              className="input-field"
              placeholder="Cole o token aqui"
              value={hfTokenInput}
              onChange={(e) => setHfTokenInput(e.target.value)}
            />
            <Button variant="secondary" onClick={handleSaveToken} disabled={savingToken || !hfTokenInput.trim()}>
              Salvar
            </Button>
          </div>
        </div>
      )}

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

/** Seletor de motor + voz de TTS, reutilizado pelo card de voz e pelo de vídeo. */
function useTtsSelection() {
  const [engine, setEngine] = useState<TtsEngine>("edge");
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [voiceId, setVoiceId] = useState("");
  const [loadingVoices, setLoadingVoices] = useState(false);

  useEffect(() => {
    setLoadingVoices(true);
    setVoiceId("");
    api
      .getVoices(engine)
      .then(setVoices)
      .catch(() => setVoices([]))
      .finally(() => setLoadingVoices(false));
  }, [engine]);

  return { engine, setEngine, voices, voiceId, setVoiceId, loadingVoices };
}

function TtsEngineAndVoiceFields({
  engine,
  setEngine,
  voices,
  voiceId,
  setVoiceId,
  loadingVoices,
}: ReturnType<typeof useTtsSelection>) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="text-xs text-slate-400">Motor de voz</label>
        <select className="input-field mt-1" value={engine} onChange={(e) => setEngine(e.target.value as TtsEngine)}>
          <option value="edge">Neural (Edge, online, grátis)</option>
          <option value="local">Local (offline, do sistema)</option>
        </select>
      </div>
      <div>
        <label className="text-xs text-slate-400">Voz</label>
        <select className="input-field mt-1" value={voiceId} onChange={(e) => setVoiceId(e.target.value)} disabled={loadingVoices}>
          <option value="">{loadingVoices ? "Carregando..." : "Padrão"}</option>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} {v.languages.length ? `(${v.languages.join(", ")})` : ""}
            </option>
          ))}
        </select>
        {!loadingVoices && voices.length === 0 && engine === "local" && (
          <p className="mt-1 text-xs text-slate-500">
            Nenhuma voz extra detectada. Windows: Configurações → Hora e idioma → Fala → Adicionar vozes.
          </p>
        )}
      </div>
    </div>
  );
}

function TtsCard() {
  const [text, setText] = useState("");
  const [rate, setRate] = useState("");
  const selection = useTtsSelection();
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  async function handleGenerate() {
    if (!text.trim()) return;
    setBusy(true);
    setAudioUrl(null);
    setStatus("Gerando áudio...");
    try {
      const job = await api.createTts(text, selection.engine, Number(rate) || 0, selection.voiceId || undefined);
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
      <CardSubtitle>Gera um áudio narrado — vozes neurais (online, grátis) ou do sistema (offline).</CardSubtitle>

      <textarea
        className="input-field mt-4 min-h-[120px] resize-y"
        placeholder="Digite o texto que vai virar narração..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="mt-3">
        <TtsEngineAndVoiceFields {...selection} />
      </div>

      <div className="mt-3">
        <label className="text-xs text-slate-400">
          Velocidade ({selection.engine === "edge" ? "% de ajuste, ex: 20 ou -20" : "palavras por minuto, ex: 150"})
        </label>
        <input className="input-field mt-1" placeholder="em branco = padrão" value={rate} onChange={(e) => setRate(e.target.value)} />
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

function TextToVideoCard() {
  const [text, setText] = useState("");
  const [rate, setRate] = useState("");
  const selection = useTtsSelection();
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [logUrl, setLogUrl] = useState<string | null>(null);

  const [hasPexelsKey, setHasPexelsKey] = useState<boolean | null>(null);
  const [pexelsKeyInput, setPexelsKeyInput] = useState("");
  const [savingKey, setSavingKey] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => setHasPexelsKey(s.has_pexels_key))
      .catch(() => setHasPexelsKey(false));
  }, []);

  async function handleSaveKey() {
    if (!pexelsKeyInput.trim()) return;
    setSavingKey(true);
    try {
      const s = await api.saveSettings({ pexelsApiKey: pexelsKeyInput.trim() });
      setHasPexelsKey(s.has_pexels_key);
      setPexelsKeyInput("");
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingKey(false);
    }
  }

  async function handleGenerate() {
    if (!text.trim()) return;
    setBusy(true);
    setVideoUrl(null);
    setLogUrl(null);
    setStatus("Gerando narração e buscando imagens (pode demorar alguns minutos)...");
    try {
      const job = await api.createTextToVideo(text, selection.engine, Number(rate) || 0, selection.voiceId || undefined);
      await poll(job.id);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  async function poll(jobId: string) {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const job = await api.getTextToVideo(jobId);
      if (job.status === "done") {
        setStatus("Vídeo gerado!");
        setVideoUrl(api.textToVideoUrl(jobId));
        setLogUrl(api.textToVideoLogUrl(jobId));
        setBusy(false);
        return;
      }
      if (job.status === "error") {
        setStatus(`Erro: ${job.error}`);
        setBusy(false);
        return;
      }
      await new Promise((r) => setTimeout(r, 2500));
    }
  }

  return (
    <Card className="lg:col-span-2">
      <div className="flex items-center gap-2">
        <Clapperboard className="h-4 w-4 text-accent" />
        <CardTitle>Texto para vídeo (narração + fotos automáticas)</CardTitle>
      </div>
      <CardSubtitle>
        Divide o texto em trechos, narra cada um e busca uma foto relacionada no banco gratuito Pexels para cada trecho.
      </CardSubtitle>

      {hasPexelsKey === false && (
        <div className="mt-4 rounded-lg border border-amber-700/40 bg-amber-500/10 p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-300">
            <KeyRound className="h-4 w-4" /> Chave da API do Pexels necessária
          </div>
          <p className="mt-1 text-xs text-amber-200/80">
            Grátis — crie a sua em{" "}
            <a href="https://www.pexels.com/api/" target="_blank" rel="noreferrer" className="underline">
              pexels.com/api
            </a>{" "}
            (leva 1 minuto, sem cartão). Ela fica salva localmente, não precisa colar de novo.
          </p>
          <div className="mt-2 flex gap-2">
            <input
              className="input-field"
              placeholder="Cole a chave aqui"
              value={pexelsKeyInput}
              onChange={(e) => setPexelsKeyInput(e.target.value)}
            />
            <Button variant="secondary" onClick={handleSaveKey} disabled={savingKey || !pexelsKeyInput.trim()}>
              Salvar
            </Button>
          </div>
        </div>
      )}

      <textarea
        className="input-field mt-4 min-h-[140px] resize-y"
        placeholder="Cole o texto que vai virar o vídeo narrado..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="sm:col-span-2">
          <TtsEngineAndVoiceFields {...selection} />
        </div>
        <div>
          <label className="text-xs text-slate-400">Velocidade</label>
          <input className="input-field mt-1" placeholder="em branco = padrão" value={rate} onChange={(e) => setRate(e.target.value)} />
        </div>
      </div>

      <Button className="mt-4" onClick={handleGenerate} disabled={!text.trim() || busy}>
        {busy ? "Gerando..." : "Gerar vídeo"}
      </Button>

      {status && <p className="mt-3 text-sm text-slate-400">{status}</p>}

      {videoUrl && (
        <div className="mt-3 space-y-2">
          <video src={videoUrl} controls className="max-h-[60vh] w-full max-w-md rounded-lg" />
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => window.open(videoUrl, "_blank")}>
              <Download className="h-4 w-4" /> Baixar vídeo
            </Button>
            {logUrl && (
              <Button variant="ghost" onClick={() => window.open(logUrl, "_blank")}>
                Ver buscas de imagem usadas
              </Button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
