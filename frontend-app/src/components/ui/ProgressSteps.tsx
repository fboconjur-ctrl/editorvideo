import { Check, Loader2, X, Circle } from "lucide-react";

export interface StepDef {
  key: string;
  label: string;
}

export type StepState = "pending" | "active" | "done" | "error";

interface ProgressStepsProps {
  steps: StepDef[];
  states: Record<string, StepState>;
}

const ICONS: Record<StepState, React.ReactNode> = {
  pending: <Circle className="h-4 w-4 text-slate-600" />,
  active: <Loader2 className="h-4 w-4 animate-spin text-accent" />,
  done: <Check className="h-4 w-4 text-emerald-400" />,
  error: <X className="h-4 w-4 text-red-400" />,
};

const TEXT_CLASSES: Record<StepState, string> = {
  pending: "text-slate-600",
  active: "text-accent font-medium",
  done: "text-emerald-400",
  error: "text-red-400 font-medium",
};

export function ProgressSteps({ steps, states }: ProgressStepsProps) {
  return (
    <ul className="space-y-1">
      {steps.map((step) => {
        const state = states[step.key] ?? "pending";
        return (
          <li key={step.key} className={`flex items-center gap-2.5 text-sm ${TEXT_CLASSES[state]}`}>
            {ICONS[state]}
            {step.label}
          </li>
        );
      })}
    </ul>
  );
}
