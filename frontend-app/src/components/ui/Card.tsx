import { HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-2xl border border-base-700 bg-base-850 p-5 shadow-panel ${className}`}
      {...props}
    />
  );
}

export function CardTitle({ className = "", ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={`text-sm font-semibold text-slate-100 ${className}`} {...props} />;
}

export function CardSubtitle({ className = "", ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={`mt-1 text-xs text-slate-400 ${className}`} {...props} />;
}
