import { StatusPill } from "./StatusPill.jsx";

export function SystemStatus({ cameraOnline, backendStatus, modelLoaded, personDetections }) {
  return (
    <section className="panel system-panel">
      <header className="panel-header compact">
        <h2>System status</h2>
      </header>
      <div className="system-grid">
        <StatusPill tone={cameraOnline ? "good" : "muted"}>Camera {cameraOnline ? "Online" : "Offline"}</StatusPill>
        <StatusPill tone={backendStatus.online ? "good" : "danger"}>Backend {backendStatus.online ? "Online" : "Offline"}</StatusPill>
        <StatusPill tone={modelLoaded ? "good" : "warn"}>AI Model {modelLoaded ? "Loaded" : "Not loaded"}</StatusPill>
        <StatusPill tone={backendStatus.online ? "good" : "danger"}>Network {backendStatus.online ? "OK" : "Error"}</StatusPill>
      </div>
      <p className="system-note">{backendStatus.message} · People detected: {personDetections}</p>
    </section>
  );
}
