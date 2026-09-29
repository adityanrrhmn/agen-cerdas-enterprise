import { useEffect, useRef, useState } from "react";
import { ChevronDown, FileText, Moon, Plus, Settings, Sun } from "lucide-react";
import { api, type Campaign, type CampaignSummary } from "./api";
import { usePoll } from "./hooks";
import Connections from "./pages/Connections";
import Monitor from "./pages/Monitor";
import Review from "./pages/Review";
import Setup from "./pages/Setup";
import { Empty, Notice } from "./ui";

type Tab = "setup" | "review" | "monitor" | "koneksi";

const STATUS_LABEL: Record<Campaign["status"], string> = { DRAFT: "Draf", RUNNING: "Berjalan", PAUSED: "Dijeda", COMPLETED: "Selesai" };
const STATUS_TONE: Record<Campaign["status"], string> = { DRAFT: "tone-neutral", RUNNING: "tone-info", PAUSED: "tone-review", COMPLETED: "tone-done" };

function CampaignStatusBadge({ status }: { status: Campaign["status"] }) {
  return <span className={`badge ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;
}

function fmtCampaignDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function CampaignPicker({ list, campaignId, isNew, onSelect }: {
  list: CampaignSummary[];
  campaignId: string | null;
  isNew: boolean;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const current = !isNew ? list.find((c) => c.campaign.campaign_id === campaignId) ?? null : null;

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => { if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); buttonRef.current?.focus(); } };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    const idx = Math.max(0, list.findIndex((c) => c.campaign.campaign_id === campaignId));
    setActiveIndex(idx);
    listRef.current?.focus();
    return () => { document.removeEventListener("mousedown", onDocClick); document.removeEventListener("keydown", onKey); };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const move = (delta: number) => {
    setActiveIndex((i) => {
      const next = Math.min(Math.max(i + delta, 0), list.length - 1);
      (listRef.current?.children[next] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest" });
      return next;
    });
  };

  const commit = (id: string) => { onSelect(id); setOpen(false); buttonRef.current?.focus(); };

  const onListKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Home") { e.preventDefault(); setActiveIndex(0); }
    else if (e.key === "End") { e.preventDefault(); setActiveIndex(list.length - 1); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); const c = list[activeIndex]; if (c) commit(c.campaign.campaign_id); }
  };

  const activeId = list[activeIndex] ? `campaign-opt-${list[activeIndex].campaign.campaign_id}` : undefined;

  return (
    <div className="campaign-select" ref={rootRef}>
      <span id="campaign-label" className="sr-only">Campaign aktif</span>
      <button ref={buttonRef} type="button" className="campaign-trigger" aria-haspopup="listbox" aria-expanded={open}
        aria-controls="campaign-listbox" aria-labelledby="campaign-label campaign-trigger-value"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => { if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(true); } }}>
        <span id="campaign-trigger-value" className="campaign-trigger-value" title={isNew ? undefined : current?.campaign.name}>
          {isNew ? "+ Campaign baru" : current ? current.campaign.name : list.length ? "Pilih campaign" : "Belum ada campaign"}
        </span>
        {current && <CampaignStatusBadge status={current.campaign.status} />}
        <ChevronDown size={16} aria-hidden className="campaign-trigger-chevron" />
      </button>
      {open && (
        <ul id="campaign-listbox" role="listbox" aria-label="Daftar campaign" aria-activedescendant={activeId}
          ref={listRef} tabIndex={-1} className="campaign-listbox" onKeyDown={onListKeyDown}>
          {list.length === 0 && <li className="campaign-option-empty">Belum ada campaign — buat lewat langkah Setup.</li>}
          {list.map((c, i) => {
            const selected = !isNew && c.campaign.campaign_id === campaignId;
            return (
              <li key={c.campaign.campaign_id} id={`campaign-opt-${c.campaign.campaign_id}`} role="option" aria-selected={selected}
                className={`campaign-option ${i === activeIndex ? "is-active" : ""} ${selected ? "is-selected" : ""}`}
                onMouseEnter={() => setActiveIndex(i)} onClick={() => commit(c.campaign.campaign_id)}>
                <span className="campaign-option-main">
                  <span className="campaign-option-name">{c.campaign.name}</span>
                  <span className="campaign-option-meta">{fmtCampaignDate(c.campaign.created_at)} · {c.counts.imported} lead</span>
                </span>
                <CampaignStatusBadge status={c.campaign.status} />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
const STEPS: { key: Tab; n?: number; label: string }[] = [
  { key: "setup", n: 1, label: "Setup" },
  { key: "monitor", n: 2, label: "Monitor" },
  { key: "review", n: 3, label: "Preview & Approval" },
];
const ALL_TABS: Tab[] = ["setup", "review", "monitor", "koneksi"];

function readUrl() {
  const p = new URLSearchParams(window.location.search);
  const tab = (p.get("tab") as Tab) || "setup";
  const google = p.get("google");
  return { tab: ALL_TABS.includes(tab) ? tab : "setup", google: google ? { status: google, detail: p.get("detail") ?? "" } : null };
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
  const [theme, setTheme] = useState<"light" | "dark">(() => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    store("theme", next);
  };
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
  const draftMode = sys?.delivery.mode === "draft";
  const connection = !sys ? null
    : sys.integrations.every((i) => i.mode === "live" || (draftMode && i.name === "gmail")) && (draftMode || sys.google.connected) ? "ok" : "partial";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden><img src="/logo-icon-square.png" alt="" /></span>
          <div>
            <p className="brand-name">Outreach Control</p>
            <p className="brand-sub">Email Writer &amp; Enrichment · Kelompok 1</p>
          </div>
        </div>
        <div className="campaign-picker">
          <CampaignPicker list={list} campaignId={campaignId} isNew={campaignId === "new"} onSelect={select} />
          <button className="btn btn-ghost btn-sm on-dark" onClick={() => { select("new"); setTab("setup"); }}>
            <Plus size={15} aria-hidden /><span>Baru</span>
          </button>
        </div>
        {draftMode && (
          <button className="mode-chip" onClick={() => setTab("koneksi")} title={sys?.delivery.reason}>
            <FileText size={14} aria-hidden /> Mode draf · email tidak dikirim
          </button>
        )}
        <button type="button" className="theme-toggle" onClick={toggleTheme} aria-pressed={theme === "dark"}
          aria-label="Mode gelap" title={theme === "dark" ? "Ganti ke mode terang" : "Ganti ke mode gelap"}>
          {theme === "dark" ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
        </button>
        <button className={`settings-gear ${connection ?? ""}`} onClick={() => setTab("koneksi")}
          title={!sys ? "Menghubungi backend" : connection === "ok" ? `Semua layanan siap · ${sys.storage.backend === "sheets" ? "Google Sheets" : "file lokal"}` : "Periksa koneksi"}
          aria-label="Pengaturan koneksi">
          <Settings size={18} aria-hidden />
          <span className="dot" aria-hidden />
        </button>
      </header>

      <nav className="steps" aria-label="Langkah">
        <div className="steps-group">
          {STEPS.map((s) => (
            <button key={s.key} className={`step ${tab === s.key ? "is-active" : ""} ${s.n ? "" : "step-aux"}`} aria-current={tab === s.key ? "page" : undefined} onClick={() => setTab(s.key)}>
              {s.n && <span className="step-n">{s.n}</span>}
              {s.key === "review" && draftMode ? "Preview & Finalisasi" : s.label}
            </button>
          ))}
        </div>
        {summary && (
          <span className="steps-meta">
            <span className="num">{summary.counts.imported}</span> lead · <span className="num">{summary.counts.pass}</span> lolos · <span className="num">{summary.counts.review}</span> review · <span className="num">{summary.counts.block}</span> blokir
          </span>
        )}
      </nav>

      <main className="main">
        <header className="page-intro">
          <div>
            <p className="page-eyebrow">OUTREACH WORKSPACE <span>/</span> {{ setup: "01 · BRIEF", monitor: "02 · STUDIO", review: "03 · EDITOR", koneksi: "PENGATURAN" }[tab]}</p>
            <h1>{{ setup: "Mulai dari sebuah pesan.", monitor: "Di balik setiap pesan.", review: "Sentuhan terakhir, dari Anda.", koneksi: "Terhubung untuk bekerja." }[tab]}</h1>
            <p className="page-description">{{ setup: "Tentukan siapa yang ingin Anda jangkau dan apa yang ingin disampaikan. Agen menyiapkan sisanya.", monitor: "Ikuti pekerjaan tim agen, dari pencarian identitas sampai draf siap ditinjau.", review: "Baca drafnya, telusuri buktinya, lalu tentukan apakah pesannya sudah tepat.", koneksi: "Kelola layanan yang membantu agen mencari, menulis, dan menyiapkan email." }[tab]}</p>
          </div>
          <span className="page-flourish" aria-hidden="true">↗</span>
        </header>
        {system.error && <Notice tone="error" title="Backend tidak terhubung">{system.error}</Notice>}
        {simulated && <Notice tone="warn" title="Mode simulasi aktif">Sebagian layanan memakai data fiktif (SIMULATE_INTEGRATIONS=true). Hasilnya bukan data sungguhan.</Notice>}
        {tab === "setup" && (
          <Setup summary={campaignId === "new" ? null : summary} system={sys}
            onCreated={(id) => { select(id); campaigns.refresh(); }} onChanged={campaigns.refresh} onStarted={() => { campaigns.refresh(); setTab("monitor"); }} />
        )}
        {(tab === "review" || tab === "monitor") && !summary && (
          <section className="panel"><Empty title="Belum ada campaign dipilih">Buat campaign dan jalankan agen di langkah Setup.</Empty></section>
        )}
        {tab === "review" && summary && <Review summary={summary} onChanged={campaigns.refresh} draftMode={draftMode} />}
        {tab === "monitor" && summary && <Monitor key={summary.campaign.campaign_id} summary={summary} draftMode={draftMode} unavailable={!!campaigns.error} />}
        {tab === "koneksi" && sys && <Connections system={sys} onChanged={system.refresh} googleResult={googleResult} />}
      </main>
    </div>
  );
}
