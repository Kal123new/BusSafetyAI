import { useEffect, useMemo, useRef, useState } from "react";
import { Camera } from "lucide-react";
import { predictFrame } from "../api/client.js";
import { StatusPill } from "./StatusPill.jsx";
import { PanelExpandButton } from './PanelExpandButton.jsx';
import { browserInference, loadBrowserModel } from '../inference/browser.js';

function normalizeDetection(detection) {
  return {
    id: `${detection.class_name}-${detection.confidence}-${detection.x}-${detection.y}`,
    class_name: detection.class_name,
    confidence: detection.confidence,
    x: detection.x,
    y: detection.y,
    width: detection.width,
    height: detection.height
  };
}

function isBlankFrame(context, width, height) {
  const sampleWidth = Math.min(width, 96);
  const sampleHeight = Math.min(height, 54);
  const sample = document.createElement('canvas'); sample.width = sampleWidth; sample.height = sampleHeight;
  const sampleContext = sample.getContext('2d');
  sampleContext.drawImage(context.canvas, 0, 0, sampleWidth, sampleHeight);
  const imageData = sampleContext.getImageData(0, 0, sampleWidth, sampleHeight).data;
  let totalBrightness = 0;
  let totalSquared = 0;
  const pixels = imageData.length / 4;

  for (let index = 0; index < imageData.length; index += 4) {
    const brightness = (imageData[index] + imageData[index + 1] + imageData[index + 2]) / 3;
    totalBrightness += brightness;
    totalSquared += brightness * brightness;
  }

  const mean = totalBrightness / pixels;
  const variance = totalSquared / pixels - mean * mean;
  const standardDeviation = Math.sqrt(Math.max(variance, 0));

  return mean < 6 && standardDeviation < 4;
}

export function LiveDetection({ backendOnline, modelLoaded, onCameraStatusChange, onDetections, onObservation = () => {}, expanded, onToggleExpand }) {
  const [browserReady, setBrowserReady] = useState(false);
  const [browserError, setBrowserError] = useState('');
  const [executionProvider, setExecutionProvider] = useState('');
  if (browserInference) { backendOnline = true; modelLoaded = browserReady; }
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [cameraEnabled, setCameraEnabled] = useState(false);
  useEffect(() => {
    if (!browserInference || !cameraEnabled) return;
    let active = true; setBrowserError('');
    loadBrowserModel().then(result => { if (active) { setBrowserReady(true); setExecutionProvider(result.provider); } })
      .catch(error => { if (active) { setBrowserReady(false); setBrowserError(error.message); } });
    return () => { active = false; };
  }, [cameraEnabled]);
  const [facingMode, setFacingMode] = useState("user");
  const [cameraState, setCameraState] = useState("off");
  const [cameraError, setCameraError] = useState("");
  const [detections, setDetections] = useState([]);
  const [lastPredictionError, setLastPredictionError] = useState("");
  const [frameWarning, setFrameWarning] = useState("");
  const [videoAspectRatio, setVideoAspectRatio] = useState(16 / 9);
  const [hasValidFrame, setHasValidFrame] = useState(false);
  const [inferenceBusy, setInferenceBusy] = useState(false);
  const lastValidAt = useRef(0);
  const observationCallback = useRef(onObservation);
  observationCallback.current = onObservation;

  useEffect(() => {
    const timer = setInterval(() => {
      if (lastValidAt.current && Date.now() - lastValidAt.current > 3500) {
        lastValidAt.current = 0; setHasValidFrame(false); setDetections([]);
        observationCallback.current(null);
      }
    }, 500);
    return () => clearInterval(timer);
  }, []);

  const personDetections = useMemo(
    () => detections.filter((detection) => detection.class_name?.toLowerCase() === "person"),
    [detections]
  );

  const averageConfidence = useMemo(() => {
    if (!personDetections.length) return null;
    const total = personDetections.reduce((sum, detection) => sum + detection.confidence, 0);
    return `${((total / personDetections.length) * 100).toFixed(1)}%`;
  }, [personDetections]);

  useEffect(() => {
    let stream;
    let cancelled = false;
    setDetections([]); setHasValidFrame(false); lastValidAt.current = 0;
    setFrameWarning(''); setLastPredictionError(''); setCameraError('');
    observationCallback.current(null);
    if (!cameraEnabled) {
      setCameraState('off');
      onCameraStatusChange(false);
      return;
    }
    setCameraState('starting');

    async function startCamera() {
      try {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
          throw new Error('Camera access needs HTTPS and a supported browser. Open the secure dashboard link.');
        }
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: 1280 },
            height: { ideal: 720 }
          },
          audio: false
        });

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }
        if (cancelled) return;
        setCameraState("live");
        stream.getVideoTracks().forEach(track => { track.onended = () => { if (!cancelled) { setCameraState('blocked'); setCameraError('Camera disconnected'); onCameraStatusChange(false); } }; });
        onCameraStatusChange(true);
      } catch (error) {
        if (cancelled) return;
        stream?.getTracks().forEach(track => track.stop());
        setCameraState("blocked");
        onCameraStatusChange(false);
        setCameraError(error instanceof Error ? error.message : "Camera could not be opened.");
      }
    }

    startCamera();

    return () => {
      cancelled = true;
      onCameraStatusChange(false);
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [cameraEnabled, facingMode, onCameraStatusChange]);

  useEffect(() => {
    const pause = () => { if (document.hidden) setCameraEnabled(false); };
    document.addEventListener('visibilitychange', pause);
    return () => document.removeEventListener('visibilitychange', pause);
  }, []);

  useEffect(() => {
    if (!cameraEnabled || cameraState !== "live" || !backendOnline || !modelLoaded) {
      setDetections([]);
      setInferenceBusy(false);
      setHasValidFrame(false); observationCallback.current(null);
      onDetections([]);
      return;
    }

    let cancelled = false;
    let busy = false;
    let retryDelay = 1200, nextAttemptAt = 0;
    const controller = new AbortController();

    async function captureAndPredict() {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (
        !video ||
        !canvas ||
        video.videoWidth === 0 ||
        video.videoHeight === 0 ||
        video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
        busy || document.hidden || Date.now() < nextAttemptAt
      ) {
        return;
      }

      busy = true;
      try {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext("2d");
        const capturedAt = Date.now() / 1000;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);

        if (isBlankFrame(context, canvas.width, canvas.height)) {
          const message = "Camera frame is black or not ready. Skipping AI detection.";
          setDetections([]);
          onDetections([]);
          setHasValidFrame(false); observationCallback.current(null);
          setFrameWarning(message);
          return;
        }

        setFrameWarning("");
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.72));
        if (!blob || cancelled) return;

        const result = await predictFrame(blob, capturedAt, controller.signal);
        if (cancelled) return;
        setInferenceBusy(false); retryDelay = 1200; nextAttemptAt = 0;
        if (result.frame_status && result.frame_status !== "valid") {
          setDetections([]);
          onDetections([]);
          setHasValidFrame(false); observationCallback.current(null);
          setFrameWarning(result.frame_status === "too_dark" ? "Camera image too dark" : "Detection unavailable");
          return;
        }
        const nextDetections = (result.detections || []).map(normalizeDetection);
        setDetections(nextDetections);
        lastValidAt.current = Date.now(); setHasValidFrame(true);
        observationCallback.current(nextDetections.filter(d => d.class_name?.toLowerCase() === 'person').length);
        onDetections(nextDetections);
        setLastPredictionError("");
      } catch (error) {
        if (!cancelled) {
          if (error.status === 429) {
            // Discard this frame and capture a new one after a bounded, jittered delay.
            retryDelay = Math.min(retryDelay * 2, 6000);
            nextAttemptAt = Date.now() + Math.max(retryDelay, error.retryAfterMs || 0) + Math.random() * 200;
            setInferenceBusy(true); setLastPredictionError('');
            return;
          }
          setInferenceBusy(false);
          setDetections([]);
          onDetections([]);
          setHasValidFrame(false); observationCallback.current(null);
          setLastPredictionError(error instanceof Error ? error.message : "Prediction failed.");
        }
      } finally {
        busy = false;
      }
    }

    captureAndPredict();
    const id = window.setInterval(captureAndPredict, 1200);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(id);
    };
  }, [backendOnline, cameraEnabled, cameraState, facingMode, modelLoaded, onDetections]);

  return (
    <section className="panel live-panel">
      <header className="panel-header">
        <h2><Camera size={14} /> Live AI detection</h2>
        <PanelExpandButton label="live AI detection" expanded={expanded} onToggle={onToggleExpand} />
        <div className="detection-meta">
          <StatusPill tone={modelLoaded && backendOnline && !inferenceBusy ? "good" : "warn"}>{hasValidFrame && modelLoaded && backendOnline && cameraState === "live" && !frameWarning && !lastPredictionError ? `${personDetections.length} detected` : inferenceBusy ? "AI processing" : "Detection unavailable"}</StatusPill>
          <span>Confidence: <b>{averageConfidence || "--"}</b></span>
        </div>
      </header>

      <div className="camera-controls">
        <label>Device camera<select aria-label="Device camera" value={facingMode} onChange={e => setFacingMode(e.target.value)}>
          <option value="user">Front camera</option><option value="environment">Rear camera</option>
        </select></label>
        <button onClick={() => setCameraEnabled(value => !value)}>{cameraEnabled ? 'Stop camera' : 'Enable camera'}</button>
        <p>{browserInference ? "Detection runs on this computer. Camera images stay on this device. The first use downloads the model. Camera stops when you leave this tab." : "When enabled, this device sends camera images to the SafeSense server for detection. Images are not retained as recordings. Camera stops when you leave this tab."}</p>
        {browserInference && cameraEnabled && !browserReady && <p role="status">{browserError || 'Loading the browser model… This can take a minute on first use.'}</p>}
        {browserReady && <p>Running locally with {executionProvider}</p>}
      </div>

      <div className="camera-shell">
        <div className="webcam-view" style={{ aspectRatio: videoAspectRatio }} aria-label="Live webcam preview with detection overlay">
          <video ref={videoRef} autoPlay playsInline muted onLoadedMetadata={(event) => {
            const video = event.currentTarget;
            if (video.videoWidth && video.videoHeight) setVideoAspectRatio(video.videoWidth / video.videoHeight);
          }} />
          <canvas ref={canvasRef} hidden />
          {cameraState !== "live" && (
            <div className="camera-message">
              <strong>{cameraState === "blocked" ? "Camera unavailable" : cameraState === 'off' ? 'Camera off' : "Opening camera"}</strong>
          <span>{cameraError || "Choose Enable camera, then allow access in your browser."}</span>
            </div>
          )}
          {frameWarning && (
            <div className="prediction-error">{frameWarning}</div>
          )}
          {lastPredictionError && (
            <div className="prediction-error">{lastPredictionError}</div>
          )}
          <div className="model-overlay" aria-hidden="true">
            {detections.map((detection) => (
              <div
                className={`person-box ${detection.class_name?.toLowerCase() === "person" ? "" : "other"}`}
                key={detection.id}
                style={{
                  left: `${detection.x}%`,
                  top: `${detection.y}%`,
                  width: `${detection.width}%`,
                  height: `${detection.height}%`
                }}
              >
                <span>{detection.class_name} {(detection.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>

        <div className="camera-footer">
          <span>This device's camera</span>
          <span className="fps">{cameraState === "live" ? "Live" : "Offline"}</span>
        </div>
      </div>
    </section>
  );
}
