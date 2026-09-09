import { useEffect, useRef, useState } from "react";
import { Scissors, Trash2, ArrowLeft, ArrowRight, Play, Plus, Download, X } from "lucide-react";
import { Card, CardTitle, CardSubtitle } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Dropzone } from "../components/ui/Dropzone";
import { VideoCanvas } from "../components/VideoCanvas";
import { Timeline } from "../components/Timeline";
import * as api from "../lib/api";
import type { EdlSegment, TextOverlay } from "../lib/types";

function newSegment(start: number, end: number): EdlSegment {
  return { start, end, speed: 1, volume: 1, color_filter: "none" };
}

interface ManualEditorPageProps {
  initialUploadId?: string | null;
  initialDuration?: number | null;
}

export function ManualEditorPage({ initialUploadId, initialDuration }: ManualEditorPageProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  const [uploadId, setUploadId] = useState<string | null>(null);
  const [totalDuration, setTotalDuration] = useState(0);
  const [segments, setSegments] = useState<EdlSegment[]>([]);
  const [texts, setTexts] = useState<TextOverlay[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [playingEditIndex, setPlayingEditIndex] = useState<number | null>(null);
  const [videoBox, setVideoBox] = useState({ width: 0, height: 0, videoHeight: 0 });
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [draggingTextIndex, setDraggingTextIndex] = useState<number | null>(null);

  const [newTextForm, setNewTextForm] = useState({ text: "", start: 0, end: 2, size: 36, color: "white" });

  useEffect(() => {
    if (initialUploadId && initialDuration) {
      initEditor(initialUploadId, initialDuration);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialUploadId, initialDuration]);

  function initEditor(id: string, duration: number) {
    setUploadId(id);
    setTotalDuration(duration);
    setSegments([newSegment(0, duration)]);
    setTexts([]);
    setSelectedIndex(0);
    setPlayingEditIndex(null);
    setResultUrl(null);
    setStatusMessage(`Vídeo carregado (${duration.toFixed(1)}s).`);
  }

  async function handleFile(file: File) {
    setStatusMessage("Enviando vídeo...");
    try {
      const info = await api.createUpload(file);
      initEditor(info.upload_id, info.duration);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : String(err));
    }
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

  function totalKeptDuration() {
    return segments.reduce((sum, s) => sum + (s.end - s.start), 0);
  }

  function flattenedTimeAt(index: number, originalTime: number) {
    let t = 0;
    for (let i = 0; i < index; i++) t += segments[i].end - segments[i].start;
    return t + (originalTime - segments[index].start);
  }

  function segmentAndTimeFromFlattened(flatTime: number) {
    let t = Math.max(0, flatTime);
    for (let i = 0; i < segments.length; i++) {
      const dur = segments[i].end - segments[i].start;
      if (t <= dur || i === segments.length - 1) {
        return { index: i, originalTime: segments[i].start + Math.max(0, Math.min(t, dur)) };
      }
      t -= dur;
    }
    return { index: 0, originalTime: segments[0]?.start ?? 0 };
  }

  function handleSeekFraction(fraction: number) {
    const kept = totalKeptDuration();
    if (kept <= 0) return;
    const { index, originalTime } = segmentAndTimeFromFlattened(fraction * kept);
    setSelectedIndex(index);
    setPlayingEditIndex(index);
    if (videoRef.current) videoRef.current.currentTime = originalTime;
  }

  function updateSegment(index: number, patch: Partial<EdlSegment>) {
    setSegments((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function handleSplit() {
    if (selectedIndex === null || !videoRef.current) return;
    const seg = segments[selectedIndex];
    const t = videoRef.current.currentTime;
    if (t <= seg.start + 0.05 || t >= seg.end - 0.05) {
      setStatusMessage("Posicione o player dentro do bloco selecionado antes de dividir.");
      return;
    }
    const newSeg = { ...seg, start: t };
    setSegments((prev) => {
      const copy = [...prev];
      copy[selectedIndex] = { ...seg, end: t };
      copy.splice(selectedIndex + 1, 0, newSeg);
      return copy;
    });
  }

  function handleDelete() {
    if (selectedIndex === null || segments.length <= 1) {
      setStatusMessage("Não é possível excluir o único trecho restante.");
      return;
    }
    setSegments((prev) => prev.filter((_, i) => i !== selectedIndex));
    setSelectedIndex((i) => Math.max(0, (i ?? 0) - 1));
    setPlayingEditIndex(null);
  }

  function moveSegment(direction: -1 | 1) {
    if (selectedIndex === null) return;
    const target = selectedIndex + direction;
    if (target < 0 || target >= segments.length) return;
    setSegments((prev) => {
      const copy = [...prev];
      [copy[selectedIndex], copy[target]] = [copy[target], copy[selectedIndex]];
      return copy;
    });
    setSelectedIndex(target);
  }

  function handlePlayEdit() {
    if (segments.length === 0 || !videoRef.current) return;
    setPlayingEditIndex(0);
    videoRef.current.currentTime = segments[0].start;
    videoRef.current.play();
  }

  const [playheadFraction, setPlayheadFraction] = useState<number | null>(null);

  function handleTimeUpdate() {
    if (playingEditIndex === null || !videoRef.current) return;
    const seg = segments[playingEditIndex];
    if (!seg) {
      setPlayingEditIndex(null);
      return;
    }
    if (videoRef.current.currentTime >= seg.end - 0.02) {
      const nextIndex = playingEditIndex + 1;
      if (nextIndex >= segments.length) {
        videoRef.current.pause();
        setPlayingEditIndex(null);
        return;
      }
      setPlayingEditIndex(nextIndex);
      videoRef.current.currentTime = segments[nextIndex].start;
    }
    const kept = totalKeptDuration();
    if (kept > 0) {
      setPlayheadFraction(flattenedTimeAt(playingEditIndex, videoRef.current.currentTime) / kept);
    }
  }

  function addText() {
    if (!newTextForm.text.trim()) return;
    setTexts((prev) => [
      ...prev,
      {
        text: newTextForm.text,
        start: newTextForm.start,
        end: newTextForm.end,
        x_percent: 50,
        y_percent: 85,
        font_size: newTextForm.size,
        color: newTextForm.color,
      },
    ]);
    setNewTextForm((f) => ({ ...f, text: "" }));
  }

  function onTextDragStart(e: React.MouseEvent, index: number) {
    e.preventDefault();
    setDraggingTextIndex(index);
  }

  useEffect(() => {
    if (draggingTextIndex === null) return;
    function onMove(e: MouseEvent) {
      const v = videoRef.current;
      if (!v) return;
      const rect = v.getBoundingClientRect();
      const xPercent = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
      const yPercent = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
      setTexts((prev) =>
        prev.map((t, i) => (i === draggingTextIndex ? { ...t, x_percent: xPercent, y_percent: yPercent } : t))
      );
    }
    function onUp() {
      setDraggingTextIndex(null);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [draggingTextIndex]);

  async function handleExport() {
    if (!uploadId || segments.length === 0) return;
    setExporting(true);
    setResultUrl(null);
    setStatusMessage("Enviando lista de cortes para renderização...");

    try {
      const renderJob = await api.createRender(uploadId, segments, texts);
      await pollRender(renderJob.id);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : String(err));
      setExporting(false);
    }
  }

  async function pollRender(jobId: string) {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      let job;
      try {
        job = await api.getRender(jobId);
      } catch (err) {
        setStatusMessage(err instanceof Error ? err.message : String(err));
        setExporting(false);
        return;
      }
      if (job.status === "rendering" || job.status === "queued") {
        setStatusMessage("Renderizando vídeo final...");
        await new Promise((r) => setTimeout(r, 1500));
        continue;
      }
      if (job.status === "error") {
        setStatusMessage(`Erro ao exportar: ${job.error}`);
        setExporting(false);
        return;
      }
      setStatusMessage("Exportação concluída!");
      setResultUrl(api.renderVideoUrl(jobId));
      setExporting(false);
      return;
    }
  }

  const selectedSegment = selectedIndex !== null ? segments[selectedIndex] : null;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-6">
        <Card>
          <CardTitle>Vídeo</CardTitle>
          <CardSubtitle>Corte, ajuste velocidade/volume/cor e adicione texto — arraste direto na tela.</CardSubtitle>

          {!uploadId ? (
            <div className="mt-4">
              <Dropzone onFile={handleFile} />
            </div>
          ) : (
            <>
              <div className="mt-4">
                <VideoCanvas
                  videoRef={videoRef}
                  src={resultUrl ?? (uploadId ? api.uploadVideoUrl(uploadId) : undefined)}
                  onLoadedMetadata={updateVideoBox}
                  onTimeUpdate={handleTimeUpdate}
                >
                  {!resultUrl &&
                    texts.map((t, i) => (
                      <div
                        key={i}
                        onMouseDown={(e) => onTextDragStart(e, i)}
                        className="pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2 cursor-move whitespace-nowrap rounded border border-transparent px-1.5 py-0.5 font-semibold hover:border-accent"
                        style={{
                          left: `${t.x_percent}%`,
                          top: `${t.y_percent}%`,
                          color: t.color,
                          fontSize: `${Math.min(
                            Math.max(8, t.font_size * (videoBox.height / (videoBox.videoHeight || 1))),
                            videoBox.height * 0.2
                          )}px`,
                          textShadow: "0 0 3px #000, 0 0 6px #000",
                        }}
                      >
                        {t.text}
                      </div>
                    ))}
                </VideoCanvas>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="secondary" onClick={handleSplit}>
                  <Scissors className="h-4 w-4" /> Dividir no ponto atual
                </Button>
                <Button variant="danger" onClick={handleDelete}>
                  <Trash2 className="h-4 w-4" /> Excluir selecionado
                </Button>
                <Button variant="secondary" onClick={() => moveSegment(-1)}>
                  <ArrowLeft className="h-4 w-4" /> Mover
                </Button>
                <Button variant="secondary" onClick={() => moveSegment(1)}>
                  Mover <ArrowRight className="h-4 w-4" />
                </Button>
                <Button variant="secondary" onClick={handlePlayEdit}>
                  <Play className="h-4 w-4" /> Reproduzir edição
                </Button>
              </div>

              <div className="mt-3">
                <Timeline
                  segments={segments}
                  totalDuration={totalDuration}
                  selectedIndex={selectedIndex}
                  playheadFraction={playingEditIndex !== null ? playheadFraction : null}
                  onSelect={setSelectedIndex}
                  onSeekFraction={handleSeekFraction}
                  onSegmentUpdate={updateSegment}
                />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Clique na timeline pra pular o vídeo pro ponto clicado. Arraste as bordas de um bloco pra
                cortar o início/fim.
              </p>

              {statusMessage && <p className="mt-3 text-sm text-slate-400">{statusMessage}</p>}

              {resultUrl && (
                <div className="mt-3">
                  <Button variant="secondary" onClick={() => window.open(resultUrl, "_blank")}>
                    <Download className="h-4 w-4" /> Baixar vídeo editado
                  </Button>
                </div>
              )}
            </>
          )}
        </Card>

        {uploadId && (
          <Card>
            <CardTitle>Textos na tela</CardTitle>
            <CardSubtitle>Adicione e arraste direto em cima do vídeo pra posicionar.</CardSubtitle>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <input
                className="input-field col-span-2 sm:col-span-1"
                placeholder="Texto"
                value={newTextForm.text}
                onChange={(e) => setNewTextForm((f) => ({ ...f, text: e.target.value }))}
              />
              <input
                type="number"
                className="input-field"
                placeholder="Início (s)"
                value={newTextForm.start}
                onChange={(e) => setNewTextForm((f) => ({ ...f, start: Number(e.target.value) }))}
              />
              <input
                type="number"
                className="input-field"
                placeholder="Fim (s)"
                value={newTextForm.end}
                onChange={(e) => setNewTextForm((f) => ({ ...f, end: Number(e.target.value) }))}
              />
              <input
                type="number"
                className="input-field"
                placeholder="Tamanho"
                value={newTextForm.size}
                onChange={(e) => setNewTextForm((f) => ({ ...f, size: Number(e.target.value) }))}
              />
            </div>
            <Button variant="secondary" className="mt-3" onClick={addText}>
              <Plus className="h-4 w-4" /> Adicionar texto
            </Button>

            <div className="mt-3 space-y-2">
              {texts.map((t, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-base-700 bg-base-900 px-3 py-2 text-sm">
                  <span>
                    "{t.text}" — {t.start.toFixed(1)}s a {t.end.toFixed(1)}s
                  </span>
                  <button onClick={() => setTexts((prev) => prev.filter((_, idx) => idx !== i))} className="text-slate-500 hover:text-red-400">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      <div className="space-y-6">
        {selectedSegment && (
          <Card>
            <CardTitle>Ajustes do trecho selecionado</CardTitle>
            <div className="mt-3 space-y-4">
              <div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Velocidade</span>
                  <span>{selectedSegment.speed.toFixed(2)}x</span>
                </div>
                <input
                  type="range"
                  min={0.5}
                  max={2}
                  step={0.05}
                  value={selectedSegment.speed}
                  onChange={(e) => updateSegment(selectedIndex!, { speed: Number(e.target.value) })}
                  className="w-full accent-accent"
                />
              </div>
              <div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Volume</span>
                  <span>{selectedSegment.volume.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={selectedSegment.volume}
                  onChange={(e) => updateSegment(selectedIndex!, { volume: Number(e.target.value) })}
                  className="w-full accent-accent"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400">Filtro de cor</label>
                <select
                  className="input-field mt-1"
                  value={selectedSegment.color_filter}
                  onChange={(e) =>
                    updateSegment(selectedIndex!, { color_filter: e.target.value as EdlSegment["color_filter"] })
                  }
                >
                  <option value="none">Nenhum</option>
                  <option value="vibrant">Vibrante</option>
                  <option value="bw">Preto e branco</option>
                  <option value="warm">Quente</option>
                  <option value="cool">Frio</option>
                </select>
              </div>
            </div>
          </Card>
        )}

        {uploadId && (
          <Card>
            <CardTitle>Exportar</CardTitle>
            <CardSubtitle>Renderiza tudo no servidor e disponibiliza pra baixar.</CardSubtitle>
            <Button className="mt-4 w-full justify-center" onClick={handleExport} disabled={exporting}>
              {exporting ? "Exportando..." : "Exportar vídeo"}
            </Button>
          </Card>
        )}
      </div>
    </div>
  );
}
