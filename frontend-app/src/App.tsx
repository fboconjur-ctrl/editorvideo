import { useState } from "react";
import { Clapperboard, Scissors, Wrench } from "lucide-react";
import { Tabs } from "./components/ui/Tabs";
import { AutoEditorPage } from "./pages/AutoEditorPage";
import { ManualEditorPage } from "./pages/ManualEditorPage";
import { ToolsPage } from "./pages/ToolsPage";

type TabId = "auto" | "manual" | "tools";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("auto");
  const [bridge, setBridge] = useState<{ uploadId: string; duration: number } | null>(null);

  function handleEditManually(uploadId: string, duration: number) {
    setBridge({ uploadId, duration });
    setActiveTab("manual");
  }

  return (
    <div className="min-h-screen bg-base-950">
      <header className="border-b border-base-800 bg-base-900/60 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <Clapperboard className="h-5 w-5 text-accent" />
            <span className="font-semibold text-slate-100">Video Editor Local</span>
          </div>
          <Tabs
            active={activeTab}
            onChange={(id) => setActiveTab(id as TabId)}
            tabs={[
              { id: "auto", label: "Automático", icon: <Clapperboard className="h-4 w-4" /> },
              { id: "manual", label: "Manual", icon: <Scissors className="h-4 w-4" /> },
              { id: "tools", label: "Ferramentas", icon: <Wrench className="h-4 w-4" /> },
            ]}
          />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div style={{ display: activeTab === "auto" ? "block" : "none" }}>
          <AutoEditorPage onEditManually={handleEditManually} />
        </div>
        <div style={{ display: activeTab === "manual" ? "block" : "none" }}>
          <ManualEditorPage initialUploadId={bridge?.uploadId} initialDuration={bridge?.duration} />
        </div>
        {activeTab === "tools" && <ToolsPage />}
      </main>
    </div>
  );
}
