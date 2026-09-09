import { useRef, useState } from "react";
import { UploadCloud, FileVideo } from "lucide-react";

interface DropzoneProps {
  onFile: (file: File) => void;
  fileName?: string | null;
}

export function Dropzone({ onFile, fileName }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
        dragOver ? "border-accent bg-accent-muted/40" : "border-base-600 hover:border-base-500"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*,audio/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      {fileName ? (
        <>
          <FileVideo className="h-7 w-7 text-accent" />
          <div className="text-sm text-slate-200">{fileName}</div>
          <div className="text-xs text-slate-500">Clique ou arraste outro arquivo para trocar</div>
        </>
      ) : (
        <>
          <UploadCloud className="h-7 w-7 text-slate-500" />
          <div className="text-sm text-slate-300">Clique ou arraste um vídeo aqui</div>
          <div className="text-xs text-slate-500">MP4, MOV, WebM...</div>
        </>
      )}
    </div>
  );
}
