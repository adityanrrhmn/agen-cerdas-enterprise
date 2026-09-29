import { useState, type CSSProperties } from "react";
import { Fingerprint, Search, PenLine, ShieldCheck, Network, Pause, Play } from "lucide-react";
import { AGENTS, type AgentId, type OfficeStates } from "./office-state";
import "./agent-office.css";

const ICONS = { orchestrator: Network, enrichment: Fingerprint, research: Search, writer: PenLine, security: ShieldCheck };

export default function AgentOffice({ states, demo = false }: { states: OfficeStates; demo?: boolean }) {
  const [selected, setSelected] = useState<AgentId>("orchestrator");
  const [motion, setMotion] = useState(true);
  const agent = AGENTS.find(a => a.id === selected)!;
  return <section className={`agent-office ${motion ? "" : "office-still"}`} aria-label="Ruang kerja agen">
    <header className="office-heading">
      <div><p className="office-eyebrow">OUTREACH STUDIO / {demo ? "DEMO ANIMASI" : "AKTIVITAS CAMPAIGN"}</p>
        <h2>Lima agen. Satu ruang kerja.</h2><p>Klik robot untuk mengenal tugasnya.</p></div>
      <button className="office-motion" type="button" aria-pressed={!motion} onClick={() => setMotion(v => !v)}>
        {motion ? <Pause size={14} /> : <Play size={14} />}{motion ? "Jeda animasi" : "Putar animasi"}
      </button>
    </header>
    <div className="office-room">
      <div className="office-window" aria-hidden="true"><i /><i /><i /></div>
      <div className="office-wall-sign" aria-hidden="true">OUTREACH<br /><b>CONTROL</b></div>
      <div className="office-plant plant-left" aria-hidden="true">✦</div>
      <div className="office-plant plant-right" aria-hidden="true">✦</div>
      <div className="office-stations">
        {AGENTS.map((a, i) => {
          const s = states[a.id]; const Icon = ICONS[a.id];
          return <button key={a.id} type="button" className={`office-station station-${a.id} mode-${s.mode}`}
            style={{ "--agent-color": a.color, "--agent-hue": a.hue, "--agent-delay": `${i * -0.43}s` } as CSSProperties}
            aria-pressed={selected === a.id} aria-controls="office-agent-detail" onClick={() => setSelected(a.id)}>
            <span className="office-station-art" aria-hidden="true">
              <span className="office-rug" /><span className="office-chair" />
              <img className="office-robot" src="/agents/robot-teal.png" alt="" width="1280" height="1280" draggable={false} />
              <span className="office-desk" /><span className="office-computer"><Icon size={24} /><span className="office-screen-lines"><i /><i /><i /></span></span>
              <span className="office-coffee" /><span className="office-signal"><i /><i /><i /></span>
            </span>
            <span className="office-name">{a.name}</span><span className="office-status"><i />{s.label}</span>
          </button>;
        })}
      </div>
      <span className="office-floor-label" aria-hidden="true">HUMAN + AGENTS</span>
    </div>
    <div id="office-agent-detail" className="office-detail">
      <span className="office-detail-icon" aria-hidden="true">{(() => { const Icon = ICONS[selected]; return <Icon size={22} />; })()}</span>
      <div><h3>{agent.name} <span> / {states[selected].label}</span></h3><p>{agent.job}</p></div>
    </div>
    <p className="office-footnote">{demo ? "Simulasi visual lokal · tidak memanggil layanan AI atau mengirim email." : "Status mengikuti pembaruan campaign. Gerakan menggambarkan aktivitas, bukan persentase kemajuan."}</p>
  </section>;
}
