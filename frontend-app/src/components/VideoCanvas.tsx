import { ReactNode, RefObject } from "react";

interface VideoCanvasProps {
  videoRef: RefObject<HTMLVideoElement>;
  src?: string;
  onLoadedMetadata?: () => void;
  onTimeUpdate?: () => void;
  children?: ReactNode;
  controls?: boolean;
}

/**
 * Player de vídeo com tamanho contido (nunca estoura a tela, diferente da
 * versão HTML anterior) e uma camada de overlay que se alinha exatamente
 * com a caixa renderizada do vídeo — usada para prévia de texto/legenda.
 */
export function VideoCanvas({
  videoRef,
  src,
  onLoadedMetadata,
  onTimeUpdate,
  children,
  controls = true,
}: VideoCanvasProps) {
  return (
    <div className="flex justify-center">
      <div className="relative inline-block max-w-full">
        <video
          ref={videoRef}
          src={src}
          controls={controls}
          onLoadedMetadata={onLoadedMetadata}
          onTimeUpdate={onTimeUpdate}
          className="block max-h-[60vh] max-w-full rounded-xl bg-black"
        />
        <div className="pointer-events-none absolute inset-0">{children}</div>
      </div>
    </div>
  );
}
