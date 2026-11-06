import { useEffect, useState } from 'react';
export function DesktopOnly({ children }) {
  const [supported, setSupported] = useState(() => window.innerWidth >= 1024);
  useEffect(() => { const resize = () => setSupported(window.innerWidth >= 1024); window.addEventListener('resize', resize); return () => window.removeEventListener('resize', resize); }, []);
  if (!supported) return <main className="session-screen"><h1>Open SafeSense on a computer</h1><p>This dashboard supports computers and large screens only. Use desktop Chrome or Edge and a window at least 1024 pixels wide. Phones and tablets are not supported.</p></main>;
  return children;
}
