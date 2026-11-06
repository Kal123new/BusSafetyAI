import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { SessionGate } from "./components/SessionGate.jsx";
import "./styles.css";
import { DesktopOnly } from './components/DesktopOnly.jsx';

createRoot(document.getElementById("root")).render(<DesktopOnly><SessionGate><App /></SessionGate></DesktopOnly>);
