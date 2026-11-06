import { Dot } from "lucide-react";

export function StatusPill({ children, tone = "good" }) {
  return (
    <span className={`status-pill ${tone}`}>
      <Dot size={18} strokeWidth={4} />
      {children}
    </span>
  );
}
