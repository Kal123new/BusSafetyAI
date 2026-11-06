import { Maximize2, Minimize2 } from 'lucide-react';

export function PanelExpandButton({ label, expanded, onToggle }) {
  const text = expanded ? 'Back to dashboard' : `Expand ${label}`;
  return <button type="button" className="panel-expand-button" aria-label={text}
    aria-expanded={expanded} title={text} onClick={onToggle}>
    {expanded ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
    <span>{expanded ? 'Back to dashboard' : 'Expand'}</span>
  </button>;
}
