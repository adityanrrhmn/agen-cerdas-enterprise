import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/lato/400.css";
import "@fontsource/lato/700.css";
import "./styles/base.css";
import AgentOffice from "./components/AgentOffice";
import { AGENTS, type OfficeStates } from "./components/office-state";

function Demo() {
  const [step, setStep] = useState(-1);
  useEffect(() => {
    if (step < 0 || step >= 5) return;
    const timer = window.setTimeout(() => setStep(s => s + 1), 3200);
    return () => window.clearTimeout(timer);
  }, [step]);
  const states = Object.fromEntries(AGENTS.map((a, i) => [a.id,
    step === -1 ? { mode: "idle", label: "Siap menerima tugas" }
      : step === 5 ? { mode: i === 4 ? "review" : "done", label: i === 4 ? "Menunggu review manusia" : "Tugas demo selesai" }
      : i === step || i === 0 ? { mode: "working", label: a.verb }
      : i < step ? { mode: "done", label: "Tugas demo selesai" } : { mode: "idle", label: "Menunggu giliran" },
  ])) as OfficeStates;
  return <main style={{ maxWidth: 1100, margin: "32px auto", padding: "0 16px" }}>
    <AgentOffice states={states} demo />
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
      <button className="btn btn-primary" disabled={step >= 0 && step < 5} onClick={() => setStep(0)}>Submit data contoh</button>
      <button className="btn btn-secondary" onClick={() => setStep(-1)}>Reset demo</button>
      <p style={{ fontSize: 12, color: "#526e62" }} aria-live="polite">{step === 5 ? "Draf demo siap ditinjau. Tidak ada email yang dikirim." : "Demo memakai urutan ilustratif, 3,2 detik per tahap."}</p>
    </div>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Demo />);
