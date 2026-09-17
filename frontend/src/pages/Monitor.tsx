import { useMemo, useState } from "react";
import { ArrowRightLeft, Power, Radio } from "lucide-react";
import { api, type AgentEvent, type CampaignSummary, type RuntimeInfo } from "../api";
import { useEvents, usePoll } from "../hooks";
import { Button, Empty, Notice, STAGE_LABEL, StatusBadge, fmtDate, fmtNum, fmtTime, fmtUsd, useAction } from "../ui";

const FLOW: { label: string; stages: string[] }[] = [
  { label: "Antre", stages: ["queued", "imported"] },
  { label: "Validasi", stages: ["validate", "validated"] },
  { label: "Enrichment", stages: ["enrichment", "enriched", "identity_resolved"] },
  { label: "Riset", stages: ["research"] },
  { label: "Menulis & periksa", stages: ["writing", "security"] },
  { label: "Review identitas", stages: ["identity_review"] },
  { label: "Diputuskan", stages: ["decided", "blocked", "failed"] },
];

export default function Monitor({ summary }: { summary: CampaignSummary }) {
  const id = summary.campaign.campaign_id;
  const runtimes = usePoll(() => api.runtimes(), 1500, []);
  const metrics = usePoll(() => api.metrics(), 3000, []);
  const queue = usePoll(() => api.queue(id), 3000, [id]);
  const { events, live } = useEvents();

  const stages = summary.stages;
  const flow = FLOW.map((f) => ({ ...f, n: f.stages.reduce((sum, s) => sum + (stages[s] ?? 0), 0) }));
  const m = metrics.data;

  return (
    <div className="monitor">
      <section className="panel flow" aria-label="Alur task per tahap">
        <header className="panel-head">
          <h2>Alur task · {summary.occurrence_id}</h2>
          <span className="muted small">{fmtNum(summary.counts.tasks)} task · rata-rata persiapan {fmtNum(summary.prep_seconds.avg, 1)} dtk · p95 {fmtNum(summary.prep_seconds.p95, 1)} dtk (n={summary.prep_seconds.n})</span>
        </header>
        <ol className="flow-steps">
          {flow.map((f) => (
            <li key={f.label} className={f.n ? "has-items" : ""}>
              <span className="flow-n">{fmtNum(f.n)}</span>
              <span className="flow-label">{f.label}</span>
            </li>
          ))}
        </ol>
      </section>

      <div className="monitor-grid">
        <div className="col">
          {runtimes.error && <Notice tone="error">{runtimes.error}</Notice>}
          <div className="runtimes">
            {(runtimes.data?.runtimes ?? []).map((r) => (
              <RuntimePanel key={r.name} runtime={r} others={runtimes.data!.runtimes.filter((x) => x.name !== r.name && x.online)} onChanged={runtimes.refresh} />
            ))}
          </div>
          <section className="panel">
            <header className="panel-head"><h2>Riwayat migrasi</h2><span className="muted small">{fmtNum(m?.migrations ?? 0)} kali</span></header>
            {runtimes.data?.migrations.length ? (
              <table className="table compact">
                <thead><tr><th>Waktu</th><th>Task</th><th>Arah</th><th className="num">Gen</th><th>Checkpoint</th><th className="num">Overhead</th></tr></thead>
                <tbody>
                  {runtimes.data.migrations.map((mg, i) => (
                    <tr key={i}>
                      <td className="mono">{fmtTime(mg.at)}</td>
                      <td>{mg.lead_id.split("-").pop()}<span className="cell-sub">{mg.reason}</span></td>
                      <td>{mg.from} → {mg.to}</td>
                      <td className="num">{mg.generation}</td>
                      <td>{mg.checkpoint.map((s) => STAGE_LABEL[s] ?? s).join(", ") || "–"}</td>
                      <td className="num">{fmtNum(mg.overhead_ms)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty title="Belum ada migrasi">Pindahkan task yang sedang berjalan, atau matikan satu runtime untuk melihat checkpoint dan generation baru.</Empty>}
          </section>
          <section className="panel">
            <header className="panel-head"><h2>Antrean kirim</h2><span className="muted small">bertahap, jeda antar-email diatur di .env</span></header>
            {queue.data?.length ? (
              <table className="table compact">
                <thead><tr><th>Lead</th><th>Penerima</th><th>Jadwal</th><th>Status</th></tr></thead>
                <tbody>
                  {queue.data.map((q) => (
                    <tr key={q.send_key}>
                      <td>{q.lead_id.split("-").pop()}<span className="cell-sub">{q.occurrence_id}</span></td>
                      <td>{q.to_email}{q.error && <span className="cell-sub warn-text">{q.error}</span>}</td>
                      <td className="mono">{fmtDate(q.schedule)}</td>
                      <td><StatusBadge status={q.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty title="Antrean kosong">Draft yang disetujui muncul di sini sampai terkirim.</Empty>}
          </section>
        </div>

        <div className="col">
          <section className="panel usage">
            <header className="panel-head"><h2>Pemakaian</h2><span className="muted small">sejak backend dijalankan</span></header>
            {m ? (
              <dl className="usage-grid">
                <div><dt>Biaya LLM campaign</dt><dd className="num">{fmtUsd(summary.cost_usd)}</dd></div>
                <div><dt>Token masuk / keluar</dt><dd className="num">{fmtNum(m.tokens_in)} / {fmtNum(m.tokens_out)}</dd></div>
                <div><dt>Pesan antaragen</dt><dd className="num">{fmtNum(m.messages)}</dd></div>
                <div><dt>Insiden injection</dt><dd className="num">{fmtNum(m.incidents)}</dd></div>
                {["openrouter", "apify", "firecrawl", "gmail"].map((p) => (
                  <div key={p}><dt>Panggilan {p}</dt><dd className="num">{fmtNum(m.api_calls[p] ?? 0)}{m.api_errors[p] ? <span className="warn-text"> · {m.api_errors[p]} galat</span> : null}</dd></div>
                ))}
              </dl>
            ) : <div className="skeleton-detail short" />}
          </section>
          <MessageLog events={events} live={live} />
        </div>
      </div>
    </div>
  );
}

function RuntimePanel({ runtime, others, onChanged }: { runtime: RuntimeInfo; others: RuntimeInfo[]; onChanged: () => void }) {
  const { busy, run } = useAction();
  const load = Math.min(100, Math.round((runtime.active / runtime.capacity) * 100));
  return (
    <section className={`panel runtime ${runtime.online ? "" : "is-offline"}`} aria-label={`Runtime ${runtime.name}`}>
      <header className="runtime-head">
        <div>
          <h2>Runtime {runtime.name}</h2>
          <p className="muted small">{runtime.online ? "online" : "offline"} · {runtime.capacity} worker · {fmtNum(runtime.completed)} selesai · rata-rata {fmtNum(runtime.avg_seconds, 1)} dtk</p>
        </div>
        <Button size="sm" variant={runtime.online ? "ghost" : "secondary"} icon={<Power size={14} />} busy={busy === "power"}
          onClick={() => run("power", () => api.setOnline(runtime.name, !runtime.online),
            (r) => runtime.online ? `Runtime ${runtime.name} dimatikan; ${r.moved} task dipindah dari checkpoint.` : `Runtime ${runtime.name} online.`).then(onChanged)}>
          {runtime.online ? "Matikan" : "Nyalakan"}
        </Button>
      </header>
      <div className="slots" role="img" aria-label={`${runtime.active} dari ${runtime.capacity} worker aktif`}>
        {Array.from({ length: runtime.capacity }, (_, i) => <span key={i} className={i < runtime.active ? "slot on" : "slot"} />)}
        <span className="slot-text">{runtime.active} aktif · {runtime.queued} antre · {load}%</span>
      </div>
      {runtime.tasks.length ? (
        <ul className="rt-tasks">
          {runtime.tasks.map((t) => (
            <li key={t.task_id}>
              <span className={`rt-state ${t.active ? "on" : ""}`}>{t.active ? "jalan" : "antre"}</span>
              <span className="rt-lead">{t.lead_id.split("-").pop()}</span>
              <span className="muted small">{STAGE_LABEL[t.stage] ?? t.stage} · gen {t.generation}</span>
              {others.map((o) => (
                <Button key={o.name} size="sm" variant="ghost" icon={<ArrowRightLeft size={13} />} busy={busy === t.task_id}
                  onClick={() => run(t.task_id, () => api.migrate(t.task_id, o.name), (mg) => `Dipindah ke ${o.name}, generation ${mg.generation}.`).then(onChanged)}>
                  ke {o.name}
                </Button>
              ))}
            </li>
          ))}
        </ul>
      ) : <p className="muted small rt-idle">Tidak ada task enrichment/riset di runtime ini.</p>}
    </section>
  );
}

const PERF_FILTERS = ["semua", "negosiasi", "hasil", "keputusan", "migrasi & kirim"] as const;

function MessageLog({ events, live }: { events: AgentEvent[]; live: boolean }) {
  const [filter, setFilter] = useState<(typeof PERF_FILTERS)[number]>("semua");
  const shown = useMemo(() => {
    const match = (e: AgentEvent) => {
      const p = e.performative ?? "";
      switch (filter) {
        case "negosiasi": return ["CFP", "PROPOSE", "ACCEPT_PROPOSAL", "REJECT_PROPOSAL"].includes(p);
        case "hasil": return ["INFORM_RESULT", "INFORM", "REQUEST"].includes(p);
        case "keputusan": return ["PASS", "REVIEW", "BLOCK"].includes(p) || e.type === "approval" || e.type === "incident";
        case "migrasi & kirim": return ["migration", "send", "runtime"].includes(e.type);
        default: return true;
      }
    };
    return events.filter(match).slice(-150).reverse();
  }, [events, filter]);

  return (
    <section className="panel log">
      <header className="panel-head">
        <h2>Pesan antaragen</h2>
        <span className={`live ${live ? "on" : ""}`}><Radio size={13} aria-hidden /> {live ? "langsung" : "terputus"}</span>
      </header>
      <div className="chips" role="tablist" aria-label="Saring pesan">
        {PERF_FILTERS.map((f) => <button key={f} role="tab" aria-selected={filter === f} className="chip" onClick={() => setFilter(f)}>{f}</button>)}
      </div>
      {shown.length ? (
        <ol className="events">
          {shown.map((e) => (
            <li key={e.id} className={`ev ev-${e.type}`}>
              <span className="mono ev-time">{fmtTime(e.ts)}</span>
              {e.performative ? <span className={`perf perf-${e.performative}`}>{e.performative}</span> : <span className="perf perf-sys">{e.type}</span>}
              <span className="ev-text">
                {e.sender && <span className="ev-route">{e.sender} → {e.receiver}</span>}
                {e.text}
              </span>
            </li>
          ))}
        </ol>
      ) : <Empty title="Belum ada pesan">Jalankan campaign; CFP, proposal, hasil, dan keputusan Security tampil di sini secara langsung.</Empty>}
    </section>
  );
}
