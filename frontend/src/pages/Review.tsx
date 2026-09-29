import { Fragment, useEffect, useMemo, useState } from "react";
import { Ban, Check, ClipboardCopy, Copy, Download, ExternalLink, FileSpreadsheet, Pause, Pencil, Play, RefreshCw, ShieldAlert, Undo2, X } from "lucide-react";
import { api, type CampaignSummary, type Email, type Evidence, type LeadDetail, type LeadRow } from "../api";
import { usePoll } from "../hooks";
import { Button, Empty, Notice, STAGE_LABEL, StatusBadge, fmtDate, fmtNum, fmtTime, fmtUsd, useAction, useToast } from "../ui";

type Filter = "all" | "ready" | "review" | "blocked" | "progress" | "sent";

const FILTERS: { key: Filter; label: string; match: (l: LeadRow) => boolean }[] = [
  { key: "all", label: "Semua", match: () => true },
  { key: "ready", label: "Siap disetujui", match: (l) => l.email_status === "AWAITING_APPROVAL" },
  { key: "review", label: "Perlu review", match: (l) => ["NEEDS_REVIEW", "NEEDS_IDENTITY", "NEEDS_REAPPROVAL", "SENT_UNKNOWN"].includes(l.email_status) },
  { key: "blocked", label: "Diblokir", match: (l) => l.email_status === "BLOCKED" || l.decision === "BLOCK" },
  { key: "progress", label: "Diproses", match: (l) => !l.email_status },
  { key: "sent", label: "Disetujui & terkirim", match: (l) => ["APPROVED", "SENDING", "SENT", "FAILED", "NOT_SENT", "FINAL"].includes(l.email_status) },
];

interface Props {
  summary: CampaignSummary;
  onChanged: () => void;
  draftMode: boolean;
}

export default function Review({ summary, onChanged, draftMode }: Props) {
  const id = summary.campaign.campaign_id;
  const leads = usePoll(() => api.leads(id), 2500, [id]);
  const [filter, setFilter] = useState<Filter>("all");
  const { busy, run } = useAction();

  const rows = leads.data ?? [];
  const counts = useMemo(() => Object.fromEntries(FILTERS.map((f) => [f.key, rows.filter(f.match).length])), [rows]);
  const visible = rows.filter(FILTERS.find((f) => f.key === filter)!.match);
  const current = visible[0] ?? null;

  const refreshAll = () => { leads.refresh(); onChanged(); };
  const paused = summary.campaign.status === "PAUSED";

  return (
    <div className="review">
      <div className="review-bar">
        <div className="segments" role="tablist" aria-label="Saring lead">
          {FILTERS.map((f) => (
            <button key={f.key} role="tab" aria-selected={filter === f.key} className={`segment seg-${f.key}`} onClick={() => setFilter(f.key)}>
              <span className="seg-count">{fmtNum(counts[f.key] ?? 0)}</span>
              <span className="seg-label">{f.key === "sent" && draftMode ? "Final" : f.label}</span>
            </button>
          ))}
        </div>
        <div className="review-actions">
          {summary.campaign.status !== "DRAFT" && summary.campaign.status !== "COMPLETED" && (
            <Button icon={paused ? <Play size={16} /> : <Pause size={16} />} busy={busy === "pause"}
              onClick={async () => { await run("pause", () => api.pause(id, !paused), paused ? "Campaign dilanjutkan." : "Campaign dijeda: agen berhenti di checkpoint berikutnya, tidak ada email terkirim."); onChanged(); }}>
              {paused ? "Lanjutkan" : "Jeda"}
            </Button>
          )}
          <a className="btn btn-secondary btn-md" href={api.exportUrl(id)} download>
            <FileSpreadsheet size={16} aria-hidden /><span>Unduh semua (CSV)</span>
          </a>
          <Button variant="primary" icon={<Check size={16} />} disabled={!counts.ready} busy={busy === "bulk"}
            onClick={async () => {
              await run("bulk", () => api.approvePass(id),
                (r) => draftMode ? `${r.approved} draf difinalkan.` : `${r.approved} draft disetujui dan masuk antrean kirim.`);
              refreshAll();
            }}>
            {draftMode ? "Finalkan" : "Setujui"} semua yang lolos ({fmtNum(counts.ready ?? 0)})
          </Button>
        </div>
      </div>
      {draftMode && (
        <Notice title="Mode draf">
          Agen menyusun dan memeriksa isi email, tetapi aplikasi tidak mengirim apa pun. Finalkan draf, lalu salin atau unduh
          (.eml / CSV) untuk dikirim dari email Anda sendiri.
        </Notice>
      )}
      {paused && <Notice tone="warn" title="Campaign dijeda">Agen berhenti di checkpoint terdekat dan scheduler tidak mengirim email.</Notice>}

      <div className="review-body">
        {leads.error && <Notice tone="error">{leads.error}</Notice>}
        {!leads.data && !leads.error && <section className="panel detail"><div className="skeleton-detail" /></section>}
        {leads.data && !current && (
          <section className="panel detail">
            <Empty title={rows.length ? "Tidak ada lead di filter ini" : "Belum ada lead"}>
              {rows.length ? "Pilih filter lain." : "Muat lead dan jalankan agen dari langkah Setup."}
            </Empty>
          </section>
        )}
        {current && <LeadPanel key={current.lead_id} leadId={current.lead_id} onChanged={refreshAll} draftMode={draftMode} />}
      </div>
    </div>
  );
}

function LeadPanel({ leadId, onChanged, draftMode }: { leadId: string; onChanged: () => void; draftMode: boolean }) {
  const detail = usePoll(() => api.lead(leadId), 3000, [leadId]);
  const d = detail.data;
  if (detail.error) return <section className="panel detail"><Notice tone="error">{detail.error}</Notice></section>;
  if (!d) return <section className="panel detail"><div className="skeleton-detail" /></section>;
  const refresh = () => { detail.refresh(); onChanged(); };
  const facts = d.evidence;
  const known = new Set(facts.map((f) => f.fact_id));
  const order = new Map((d.email?.used_fact_ids ?? []).filter((id) => known.has(id)).map((id, i) => [id, i + 1]));

  return (
    <section className="panel detail" aria-label={`Detail ${d.lead.name}`}>
      <header className="detail-head">
        <div>
          <h2>{d.lead.name}</h2>
          <p className="muted">{[d.lead.company || d.lead.hints?.organization, d.lead.email || "tanpa email"].filter(Boolean).join(" · ")}</p>
          {d.lead.description && <p className="lead-desc">“{d.lead.description}”</p>}
          {d.lead.hints && (d.lead.hints.organization || d.lead.hints.role) && (
            <p className="hint-line">
              Dibaca agen dari deskripsi: {[d.lead.hints.role, d.lead.hints.organization_aliases.join(" / ") || d.lead.hints.organization].filter(Boolean).join(" · ")}
              <span className="muted"> (petunjuk pencarian, bukan fakta email)</span>
            </p>
          )}
        </div>
        <div className="detail-status">
          <StatusBadge status={d.email?.status ?? ""} fallback={STAGE_LABEL[d.lead.stage] ?? d.lead.stage} />
          {d.lead.match_score !== null && <span className="score" title="Skor entity linking S = 0,40d + 0,30n + 0,20c + 0,10r">S {fmtNum(d.lead.match_score, 3)}</span>}
        </div>
      </header>

      <div className="review-reading">
      <div className="review-letter">
      <Reasons detail={d} />
      {!d.lead.email && <EmailFill leadId={d.lead.lead_id} onChanged={refresh} optional={draftMode} />}
      {d.email?.status === "NEEDS_IDENTITY" && <IdentityReview detail={d} onChanged={refresh} />}
      {d.email && d.email.status !== "NEEDS_IDENTITY" && <Draft email={d.email} facts={facts} order={order} onChanged={refresh} draftMode={draftMode} />}
      {!d.email && <Empty title="Agen masih bekerja">Tahap sekarang: {STAGE_LABEL[d.lead.stage] ?? d.lead.stage}{d.task?.host ? ` di runtime ${d.task.host}` : ""}.</Empty>}
      {d.email?.status === "BLOCKED" && !d.email.body && <p className="muted small">Kontak diblokir sebelum draft ditulis; tidak ada biaya LLM.</p>}

      </div>
      <aside className="review-notes" aria-label="Bukti dan riwayat draf">
        <p className="page-eyebrow">DI BALIK DRAF INI</p>
        <EvidenceList facts={facts} order={order} />
        {!facts.length && <p className="muted small">Belum ada bukti yang tersedia untuk lead ini.</p>}
        <Trail detail={d} />
      </aside>
      </div>
    </section>
  );
}

function Reasons({ detail }: { detail: LeadDetail }) {
  const reasons = detail.email?.security_reasons?.length ? detail.email.security_reasons : detail.lead.reasons;
  if (!reasons?.length && !detail.email?.error) return null;
  return (
    <div className="reasons">
      {reasons?.map((r, i) => (
        <p key={i} className={`reason reason-${r.level}`}>
          {r.level === "block" ? <Ban size={14} aria-hidden /> : r.level === "review" ? <ShieldAlert size={14} aria-hidden /> : <span className="info-dot" aria-hidden />}
          <span className="reason-level">{{ block: "Blokir", review: "Review", info: "Info" }[r.level]}</span>
          {r.message}
        </p>
      ))}
      {detail.email?.error && <p className="reason reason-review"><ShieldAlert size={14} aria-hidden /><span className="reason-level">Kirim</span>{detail.email.error}</p>}
    </div>
  );
}

function EmailFill({ leadId, onChanged, optional }: { leadId: string; onChanged: () => void; optional: boolean }) {
  const [value, setValue] = useState("");
  const { busy, run } = useAction();
  return (
    <form className={`email-fill ${optional ? "is-optional" : ""}`} onSubmit={async (e) => {
      e.preventDefault();
      const ok = await run("email", () => api.setLeadEmail(leadId, value), "Email disimpan; draft diperiksa ulang.");
      if (ok !== undefined) onChanged();
    }}>
      <label htmlFor={`email-${leadId}`}>{optional ? "Email penerima (opsional, ikut di file .eml)" : "Email penerima belum ada"}</label>
      <input id={`email-${leadId}`} type="email" required value={value} onChange={(e) => setValue(e.target.value)} placeholder="nama@instansi.ac.id" />
      <Button type="submit" size="sm" variant="primary" busy={busy === "email"}>Simpan email</Button>
    </form>
  );
}

function IdentityReview({ detail, onChanged }: { detail: LeadDetail; onChanged: () => void }) {
  const { busy, run } = useAction();
  const lead = detail.lead;
  return (
    <div className="identity">
      <h3>Pilih identitas yang benar</h3>
      <p className="muted small">
        Agen tidak menebak. Kandidat diurutkan dengan S = 0,40·domain/URL + 0,30·nama + 0,20·perusahaan + 0,10·jabatan; diterima otomatis hanya bila S ≥ 0,85 dan unggul ≥ 0,10.
        Data CRM: {lead.domain || "tanpa domain"}{lead.title_hint ? `, ${lead.title_hint}` : ""}.
      </p>
      <table className="table">
        <thead><tr><th>Kandidat</th><th className="num">d</th><th className="num">n</th><th className="num">c</th><th className="num">r</th><th className="num">S</th><th /></tr></thead>
        <tbody>
          {lead.candidates.map((c, i) => (
            <tr key={i}>
              <td>
                <strong>{c.name}</strong>
                <span className="cell-sub">{[c.title, c.company, c.domain].filter(Boolean).join(" · ")}</span>
                {c.profile_url && <a className="cell-link" href={c.profile_url} target="_blank" rel="noreferrer">Profil <ExternalLink size={12} aria-hidden /></a>}
              </td>
              <td className="num">{fmtNum(c.score.d, 0)}</td>
              <td className="num">{fmtNum(c.score.n, 2)}</td>
              <td className="num">{fmtNum(c.score.c, 2)}</td>
              <td className="num">{fmtNum(c.score.r, 2)}</td>
              <td className="num strong">{fmtNum(c.score.S, 3)}</td>
              <td><Button size="sm" busy={busy === `c${i}`} onClick={async () => { await run(`c${i}`, () => api.resolve(lead.lead_id, i), "Identitas dipilih; agen melanjutkan dari checkpoint."); onChanged(); }}>Pilih</Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button variant="ghost" busy={busy === "none"} onClick={async () => { await run("none", () => api.resolve(lead.lead_id, null), "Dilanjutkan tanpa data enrichment."); onChanged(); }}>
        Bukan salah satunya, lanjut tanpa enrichment
      </Button>
    </div>
  );
}

function highlight(body: string, facts: Evidence[], order: Map<string, number>) {
  const used = facts.filter((f) => order.has(f.fact_id) && f.value.length >= 4);
  if (!used.length) return body;
  const pattern = new RegExp(`(${used.map((f) => f.value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return body.split(pattern).map((part, i) => {
    const fact = used.find((f) => f.value.toLowerCase() === part.toLowerCase());
    return fact ? (
      <mark key={i} className="fact-mark" title={`${fact.field} · ${fact.source_type}`}>{part}<sup>{order.get(fact.fact_id)}</sup></mark>
    ) : <Fragment key={i}>{part}</Fragment>;
  });
}

function CopyTools({ email }: { email: Email }) {
  const toast = useToast();
  const copy = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast(`${label} disalin.`);
    } catch {
      toast("Browser menolak akses clipboard. Salin manual dari teks di atas.", "error");
    }
  };
  return (
    <div className="copy-tools" aria-label="Ambil hasil draf">
      <Button size="sm" icon={<Copy size={14} />} onClick={() => copy("Subjek", email.subject)}>Salin subjek</Button>
      <Button size="sm" icon={<Copy size={14} />} onClick={() => copy("Isi email", email.body)}>Salin isi</Button>
      <Button size="sm" icon={<ClipboardCopy size={14} />} onClick={() => copy("Subjek dan isi", `Subjek: ${email.subject}\n\n${email.body}`)}>Salin semua</Button>
      <a className="btn btn-secondary btn-sm" href={api.emlUrl(email.send_key)} download>
        <Download size={14} aria-hidden /><span>Unduh .eml</span>
      </a>
    </div>
  );
}

function Draft({ email, facts, order, onChanged, draftMode }: {
  email: Email; facts: Evidence[]; order: Map<string, number>; onChanged: () => void; draftMode: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const [ack, setAck] = useState(false);
  const { busy, run } = useAction();

  useEffect(() => { if (!editing) { setSubject(email.subject); setBody(email.body); } }, [email.subject, email.body, editing]);

  const canApprove = Boolean(email.body) && (email.status === "AWAITING_APPROVAL" || (email.status === "NEEDS_REVIEW" && ack));
  const editable = ["AWAITING_APPROVAL", "NEEDS_REVIEW", "APPROVED", "NEEDS_REAPPROVAL", "FINAL"].includes(email.status);
  const suppressible = Boolean(email.to_email) && !["SENT", "SENDING", "BLOCKED"].includes(email.status);
  const verb = draftMode ? "Finalkan" : "Setujui";

  return (
    <article className="draft">
      <header className="draft-head">
        <span className="draft-version">Draft v{email.draft_version}</span>
        {email.llm_model && <span className="muted small">{email.llm_model === "simulasi" ? "SIMULASI (bukan LLM)" : email.llm_model} · {fmtNum(email.tokens_in + email.tokens_out)} token · {fmtUsd(email.cost_usd)}</span>}
        <div className="draft-tools">
          {editable && !editing && (
            <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} busy={busy === "regen"}
              onClick={async () => {
                await run("regen", () => api.regenerate(email.send_key),
                  "Agen menulis ulang draft; enrichment dan riset tidak diulang.");
                onChanged();
              }}>Tulis ulang</Button>
          )}
          {editable && !editing && <Button size="sm" variant="ghost" icon={<Pencil size={14} />} onClick={() => setEditing(true)}>Edit</Button>}
        </div>
      </header>
      <dl className="mail-meta">
        <div><dt>Kepada</dt><dd>{email.to_email || (draftMode ? <span className="muted">tidak diisi (opsional)</span> : <span className="warn-text">belum diisi</span>)}</dd></div>
        <div><dt>Subjek</dt><dd>{editing ? <input value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value.replace(/[\r\n]+/g, " "))} aria-label="Subjek" /> : email.subject}</dd></div>
        {!draftMode && <div><dt>Jadwal</dt><dd>{fmtDate(email.schedule)}</dd></div>}
      </dl>
      {editing ? (
        <>
          <textarea className="mail-edit" rows={12} maxLength={20000} value={body} onChange={(e) => setBody(e.target.value)} aria-label="Isi email" />
          <div className="draft-actions">
            <Button variant="primary" busy={busy === "save"} onClick={async () => {
              const r = await run("save", () => api.editEmail(email.send_key, subject, body),
                (x) => `Tersimpan sebagai v${x.draft_version}; pemeriksaan ulang: ${x.security_decision}. ${draftMode ? "Finalisasi" : "Approval"} lama batal.`);
              if (r) { setEditing(false); onChanged(); }
            }}>Simpan &amp; periksa ulang</Button>
            <Button variant="ghost" icon={<Undo2 size={14} />} onClick={() => setEditing(false)}>Batal</Button>
          </div>
        </>
      ) : email.body ? (
        <div className="mail-body">{highlight(email.body, facts, order)}</div>
      ) : (
        <p className="muted small">Draft belum ditulis. Gunakan "Tulis ulang" untuk mencoba lagi, atau "Edit" untuk menulis manual.</p>
      )}
      {!editing && ["AWAITING_APPROVAL", "NEEDS_REVIEW"].includes(email.status) && (
        <footer className="approve-bar">
          {email.status === "NEEDS_REVIEW" && (
            <label className="ack">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              Saya sudah memeriksa alasan review dan bukti di atas
            </label>
          )}
          <div className="draft-actions">
            <Button variant="primary" icon={<Check size={16} />} disabled={!canApprove} busy={busy === "approve"}
              onClick={async () => {
                await run("approve", () => api.approve(email.send_key, email.draft_version, ack),
                  draftMode ? `Draf v${email.draft_version} final; siap disalin atau diunduh.` : `Draft v${email.draft_version} disetujui.`);
                onChanged();
              }}>
              {verb} v{email.draft_version}
            </Button>
            <Button variant="ghost" icon={<X size={16} />} busy={busy === "reject"}
              onClick={async () => { await run("reject", () => api.reject(email.send_key), draftMode ? "Draf dibuang." : "Draft ditolak; tidak akan dikirim."); onChanged(); }}>Tolak</Button>
          </div>
        </footer>
      )}
      {!editing && email.status === "FINAL" && (
        <footer className="approve-bar is-final">
          <p className="small"><strong>Draf final v{email.draft_version}.</strong> Salin atau unduh, lalu kirim dari email Anda sendiri.
            Edit akan membuka kembali pemeriksaan.</p>
        </footer>
      )}
      {!editing && draftMode && email.status !== "BLOCKED" && <CopyTools email={email} />}
      {email.status === "SENT_UNKNOWN" && (
        <footer className="approve-bar">
          <p className="small">Gmail tidak memberi hasil pasti. Periksa folder Terkirim di akun pengirim, lalu catat hasilnya. Sistem tidak mengirim ulang otomatis.</p>
          <div className="draft-actions">
            <Button busy={busy === "rs"} onClick={async () => { await run("rs", () => api.reconcile(email.send_key, "sent"), "Dicatat terkirim."); onChanged(); }}>Ada di Terkirim</Button>
            <Button busy={busy === "rn"} onClick={async () => { await run("rn", () => api.reconcile(email.send_key, "not_sent"), "Dicatat tidak terkirim."); onChanged(); }}>Tidak ada</Button>
          </div>
        </footer>
      )}
      {email.status === "SENT" && <p className="small muted sent-note">Diterima Gmail API (ID {email.gmail_id}). Ini bukan bukti email sampai atau dibaca.</p>}
      {suppressible && (
        <button className="link-danger" disabled={busy === "sup"} onClick={async () => {
          await run("sup", () => api.suppress(email.to_email, "diminta dari dashboard"), "Kontak masuk suppression dan diblokir.");
          onChanged();
        }}>
          Jangan hubungi kontak ini lagi
        </button>
      )}
    </article>
  );
}

function EvidenceList({ facts, order }: { facts: Evidence[]; order: Map<string, number> }) {
  if (!facts.length) return null;
  const label = { crm: "CRM", apify: "Apify", firecrawl: "Web" } as const;
  return (
    <section className="evidence">
      <h3>Jejak bukti</h3>
      <ol className="facts">
        {facts.map((f) => (
          <li key={f.fact_id} className={`fact ${f.selected ? "is-selected" : ""}`}>
            <span className={`fact-no ${order.has(f.fact_id) ? "is-used" : ""}`} aria-label={order.has(f.fact_id) ? `Dipakai di email, penanda ${order.get(f.fact_id)}` : "Tidak dipakai"}>
              {order.get(f.fact_id) ?? "·"}
            </span>
            <div className="fact-main">
              <p className="fact-value"><span className="fact-field">{f.field}</span>{f.value}</p>
              {f.quote && <blockquote>“{f.quote}”</blockquote>}
              <p className="fact-meta">
                <span className={`src src-${f.source_type}`}>{label[f.source_type]}</span>
                {f.source_url.startsWith("http") ? <a href={f.source_url} target="_blank" rel="noreferrer">{new URL(f.source_url).hostname} <ExternalLink size={11} aria-hidden /></a> : <span className="mono">{f.source_url}</span>}
                <span>diambil {fmtTime(f.retrieved_at)}</span>
                {f.match_score !== null && <span>S {fmtNum(f.match_score, 3)}</span>}
                {f.selected && !order.has(f.fact_id) && <span>dipilih, tidak dipakai</span>}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Trail({ detail }: { detail: LeadDetail }) {
  const t = detail.task;
  if (!t) return null;
  return (
    <details className="trail">
      <summary>Task {t.task_id} · generation {t.generation} · {t.host || "–"}</summary>
      <p className="small">Checkpoint: {(t.checkpoint.done ?? []).map((s) => STAGE_LABEL[s] ?? s).join(" → ") || "belum ada"}{t.retry ? ` · retry ${t.retry}` : ""}{t.error ? ` · galat: ${t.error}` : ""}</p>
      {detail.audit.length > 0 && (
        <ul className="audit">
          {detail.audit.map((a) => <li key={a.event_id}><span className="mono">{fmtTime(a.timestamp)}</span> <strong>{a.actor}</strong> {a.change_summary}</li>)}
        </ul>
      )}
    </details>
  );
}
