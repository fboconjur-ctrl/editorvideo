import { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

/**
 * Seção recolhível de página única — substitui a navegação por abas: em
 * vez de trocar de tela, o usuário expande só a parte que precisa usar
 * no momento, mantendo tudo na mesma página sem rolagem excessiva.
 */
export function Section({
  id,
  title,
  icon,
  expanded,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  icon: ReactNode;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div id={id} className="rounded-2xl border border-base-700 bg-base-850 shadow-panel">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-5 py-4 text-left"
      >
        <div className="flex items-center gap-2">
          {icon}
          <span className="font-semibold text-slate-100">{title}</span>
        </div>
        <ChevronDown
          className={`h-4 w-4 text-slate-400 transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>
      {/* Sempre montado (só escondido via display), pra não perder o
          progresso/estado de um editor ao fechar a seção e abrir outra. */}
      <div className="border-t border-base-800 p-5" style={{ display: expanded ? "block" : "none" }}>
        {children}
      </div>
    </div>
  );
}
