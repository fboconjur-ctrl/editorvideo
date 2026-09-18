import { useState } from "react";
import { Clapperboard, Scissors, Wrench } from "lucide-react";
import { Section } from "./components/ui/Section";
import { AutoEditorPage } from "./pages/AutoEditorPage";
import { ManualEditorPage } from "./pages/ManualEditorPage";
import { ToolsPage } from "./pages/ToolsPage";

type SectionId = "auto" | "manual" | "tools";

export default function App() {
  // Tudo fica na mesma página, sem trocar de tela — só uma seção
  // expandida por vez, pra não precisar rolar por três editores inteiros
  // ao mesmo tempo. O estado de cada editor continua vivo mesmo com a
  // seção fechada (fica só escondida via CSS), então não perde nada ao
  // alternar.
  const [expanded, setExpanded] = useState<SectionId>("auto");
  const [bridge, setBridge] = useState<{ uploadId: string; duration: number } | null>(null);

  function handleEditManually(uploadId: string, duration: number) {
    setBridge({ uploadId, duration });
    setExpanded("manual");
    requestAnimationFrame(() => {
      document.getElementById("section-manual")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function toggle(id: SectionId) {
    setExpanded((current) => (current === id ? current : id));
  }

  return (
    <div className="min-h-screen bg-base-950">
      <header className="border-b border-base-800 bg-base-900/60 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center px-6 py-4">
          <Clapperboard className="h-5 w-5 text-accent" />
          <span className="ml-2 font-semibold text-slate-100">Video Editor Local</span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-6 py-8">
        <Section
          id="section-auto"
          title="Automático"
          icon={<Clapperboard className="h-4 w-4 text-accent" />}
          expanded={expanded === "auto"}
          onToggle={() => toggle("auto")}
        >
          <AutoEditorPage onEditManually={handleEditManually} />
        </Section>

        <Section
          id="section-manual"
          title="Manual"
          icon={<Scissors className="h-4 w-4 text-accent" />}
          expanded={expanded === "manual"}
          onToggle={() => toggle("manual")}
        >
          <ManualEditorPage initialUploadId={bridge?.uploadId} initialDuration={bridge?.duration} />
        </Section>

        <Section
          id="section-tools"
          title="Ferramentas"
          icon={<Wrench className="h-4 w-4 text-accent" />}
          expanded={expanded === "tools"}
          onToggle={() => toggle("tools")}
        >
          <ToolsPage />
        </Section>
      </main>
    </div>
  );
}
