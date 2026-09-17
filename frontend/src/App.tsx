import { useEffect, useState } from "react";
import { Mail, Plus } from "lucide-react";
import { api } from "./api";
import { usePoll } from "./hooks";
import Connections from "./pages/Connections";
import Monitor from "./pages/Monitor";
import Review from "./pages/Review";
import Setup from "./pages/Setup";
import { Empty, Notice } from "./ui";

type Tab = "setup" | "review" | "monitor" | "koneksi";
const STEPS: { key: Tab; n?: number; label: string }[] = [
  { key: "setup", n: 1, label: "Setup" },
  { key: "review", n: 2, label: "Preview & Approval" },
  { key: "monitor", n: 3, label: "Monitor" },
  { key: "koneksi", label: "Koneksi" },
];

function readUrl() {
  const p = new URLSearchParams(window.location.search);
  const tab = (p.get("tab") as Tab) || "setup";
  const google = p.get("google");
  return { tab: STEPS.some((s) => s.key === tab) ? tab : "setup", google: google ? { status: google, detail: p.get("detail") ?? "" } : null };
}

function store(key: string, value?: string) {
  try {
    if (value === undefined) return window.localStorage.getItem(key);
    window.localStorage.setItem(key, value);
  } catch {
    /* penyimpanan browser tidak tersedia */
  }
  return null;
}

export default function App() {
  const initial = readUrl();
  const [tab, setTab] = useState<Tab>(initial.tab);
  const [googleResult] = useState(initial.google);
  const [campaignId, setCampaignId] = useState<string | null>(() => store("campaign"));
  const system = usePoll(() => api.system(), 5000, []);
  const campaigns = usePoll(() => api.campaigns(), 3000, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.search = tab === "setup" ? "" : `?tab=${tab}`;
    window.history.replaceState(null, "", url);
  }, [tab]);

  const list = campaigns.data ?? [];
  const summary = list.find((c) => c.campaign.campaign_id === campaignId) ?? null;

  useEffect(() => {
    if (campaigns.data && campaignId && campaignId !== "new" && !summary) setCampaignId(list[0]?.campaign.campaign_id ?? null);
    if (campaigns.data && !campaignId && list.length) setCampaignId(list[0].campaign.campaign_id);
  }, [campaigns.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = (id: string | null) => {
    setCampaignId(id);
    if (id) store("campaign", id);
  };

  const sys = system.data;
  const simulated = sys?.integrations.some((i) => i.mode === "simulasi");
  const connection = !sys ? null : sys.integrations.every((i) => i.mode === "live") && sys.google.connected ? "ok" : "partial";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden><Mail size={16} strokeWidth={2.2} /></span>
          <div>
            <p className="brand-name">Outreach Control</p>
            <p className="brand-sub">Email Writer &amp; Enrichment · Kelompok 1</p>
          </div>
        </div>
        <div className="campaign-picker">
          <label htmlFor="campaign" className="sr-only">Campaign</label>
          <select id="campaign" value={summary ? campaignId ?? "" : "new"} onChange={(e) => { select(e.target.value === "new" ? "new" : e.target.value); if (e.target.value === "new") setTab("setup"); }}>
            {list.map((c) => (
              <option key={c.campaign.campaign_id} value={c.campaign.campaign_id}>{c.campaign.name} · {c.campaign.status}</option>
            ))}
            <option value="new">+ Campaign baru</option>
          </select>
          <button className="btn btn-ghost btn-sm on-dark" onClick={() => { select("new"); setTab("setup"); }}>
            <Plus size={15} aria-hidden /><span>Baru</span>
          </button>
        </div>
        <button className={`conn-state ${connection ?? ""}`} onClick={() => setTab("koneksi")}>
          <span className="dot" aria-hidden />
          {!sys ? "Menghubungi backend" : connection === "ok" ? `Semua layanan siap · ${sys.storage.backend === "sheets" ? "Google Sheets" : "file lokal"}` : "Periksa koneksi"}
        </button>
      </header>

      <nav className="steps" aria-label="Langkah">
        {STEPS.map((s) => (
          <button key={s.key} className={`step ${tab === s.key ? "is-active" : ""} ${s.n ? "" : "step-aux"}`} aria-current={tab === s.key ? "page" : undefined} onClick={() => setTab(s.key)}>
            {s.n && <span className="step-n">{s.n}</span>}
            {s.label}
          </button>
        ))}
        {summary && (
          <span className="steps-meta">
            <span className="num">{summary.counts.imported}</span> lead · <span className="num">{summary.counts.pass}</span> lolos · <span className="num">{summary.counts.review}</span> review · <span className="num">{summary.counts.block}</span> blokir
          </span>
        )}
      </nav>

      <main className="main">
        {system.error && <Notice tone="error" title="Backend tidak terhubung">{system.error}</Notice>}
        {simulated && <Notice tone="warn" title="Mode simulasi aktif">Sebagian layanan memakai data fiktif (SIMULATE_INTEGRATIONS=true). Hasilnya bukan data sungguhan.</Notice>}
        {tab === "setup" && (
          <Setup summary={campaignId === "new" ? null : summary} system={sys}
            onCreated={(id) => { select(id); campaigns.refresh(); }} onChanged={campaigns.refresh} onStarted={() => { campaigns.refresh(); setTab("review"); }} />
        )}
        {(tab === "review" || tab === "monitor") && !summary && (
          <section className="panel"><Empty title="Belum ada campaign dipilih">Buat campaign dan jalankan agen di langkah Setup.</Empty></section>
        )}
        {tab === "review" && summary && <Review summary={summary} onChanged={campaigns.refresh} />}
        {tab === "monitor" && summary && <Monitor summary={summary} />}
        {tab === "koneksi" && sys && <Connections system={sys} onChanged={system.refresh} googleResult={googleResult} />}
      </main>
    </div>
  );
}
