import { useRef } from "react";
import type { EdlSegment } from "../lib/types";

interface TimelineProps {
  segments: EdlSegment[];
  totalDuration: number;
  selectedIndex: number | null;
  playheadFraction: number | null;
  onSelect: (index: number) => void;
  onSeekFraction: (fraction: number) => void;
  onSegmentUpdate: (index: number, patch: Partial<Pick<EdlSegment, "start" | "end">>) => void;
}

const MIN_SEGMENT_LENGTH = 0.1;

export function Timeline({
  segments,
  totalDuration,
  selectedIndex,
  playheadFraction,
  onSelect,
  onSeekFraction,
  onSegmentUpdate,
}: TimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const suppressClick = useRef(false);

  const keptDuration = segments.reduce((sum, s) => sum + (s.end - s.start), 0) || 0.01;

  function startResize(e: React.MouseEvent, index: number, side: "left" | "right") {
    e.stopPropagation();
    e.preventDefault();
    suppressClick.current = true;

    const container = containerRef.current;
    if (!container) return;
    const pxPerSec = container.clientWidth / keptDuration;
    const startX = e.clientX;
    const startVal = side === "left" ? segments[index].start : segments[index].end;

    function onMove(ev: MouseEvent) {
      const deltaSec = (ev.clientX - startX) / pxPerSec;
      const seg = segments[index];
      if (side === "left") {
        const newStart = Math.max(0, Math.min(startVal + deltaSec, seg.end - MIN_SEGMENT_LENGTH));
        onSegmentUpdate(index, { start: newStart });
      } else {
        const newEnd = Math.min(totalDuration, Math.max(startVal + deltaSec, seg.start + MIN_SEGMENT_LENGTH));
        onSegmentUpdate(index, { end: newEnd });
      }
    }
    function onUp() {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function handleClick(e: React.MouseEvent) {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    onSeekFraction((e.clientX - rect.left) / rect.width);
  }

  return (
    <div
      ref={containerRef}
      onClick={handleClick}
      className="relative flex h-16 select-none overflow-hidden rounded-xl border border-base-700 bg-base-950"
    >
      {segments.map((seg, i) => (
        <div
          key={i}
          onClick={(e) => {
            if (suppressClick.current) return;
            e.stopPropagation();
            onSelect(i);
          }}
          style={{ flex: `${Math.max(seg.end - seg.start, 0.01)} 0 0` }}
          className={`relative flex items-center justify-center overflow-hidden whitespace-nowrap border-r-2 border-base-950 text-xs font-medium text-white ${
            i === selectedIndex ? "bg-accent" : "bg-[#2f6fed] hover:brightness-110"
          }`}
        >
          <div
            onMouseDown={(e) => startResize(e, i, "left")}
            className="absolute inset-y-0 left-0 z-10 w-2.5 cursor-ew-resize bg-white/0 hover:bg-white/30"
          />
          {seg.start.toFixed(1)}s–{seg.end.toFixed(1)}s
          <div
            onMouseDown={(e) => startResize(e, i, "right")}
            className="absolute inset-y-0 right-0 z-10 w-2.5 cursor-ew-resize bg-white/0 hover:bg-white/30"
          />
        </div>
      ))}
      {playheadFraction !== null && (
        <div
          className="pointer-events-none absolute -top-1 -bottom-1 z-20 w-0.5 bg-red-500"
          style={{ left: `${Math.max(0, Math.min(100, playheadFraction * 100))}%` }}
        />
      )}
    </div>
  );
}
