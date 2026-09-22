import { useRef, useState } from "react";
import { FileUp, Play, Sparkles, User, Users } from "lucide-react";
import { api, type CampaignSummary, type SystemInfo } from "../api";
import { usePoll } from "../hooks";
import { Button, Field, Notice, fmtDate, useAction, useToast } from "../ui";
import { LeadPreviewList, ManualLeadForm } from "./ManualLead";

function nextMonday9() {
  const d = new Date();
  d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00`;
}

const INITIAL = {
  name: "Undangan demo otomasi laporan",
  goal: "Mengundang demo solusi otomasi B2B",
  offer: "Solusi untuk merangkum laporan dan mengoordinasikan tindak lanjut antar-cabang",
  cta: "Apakah Bapak/Ibu berkenan mengikuti demo singkat selama 15 menit minggu depan?",
  personalization: "per_lead",
  cadence: "once",
  max_occurrences: 4,
  count: 100,
  schedule: nextMonday9(),
  timezone: "Asia/Jakarta",
  budget: 2,
  sender_name: "Tim Penjualan",
  template_subject: "",
  template_body: "",
  single_recipient: true,
  send_now: true,
};

interface Props {
  summary: CampaignSummary | null;
  system: SystemInfo | null;
  onCreated: (id: string) => void;
  onChanged: () => void;
  onStarted: () => void;
}

export default function Setup({ summary, system, onCreated, onChanged, onStarted }: Props) {
  const campaign = summary?.campaign;
  const isDraft = !campaign || campaign.status === "DRAFT";
  return (
    <div className="setup">
      <section className="panel setup-form">
        <header className="panel-head">
          <h2>{campaign ? campaign.name : "Campaign baru"}</h2>
          {campaign && <span className="muted mono">{campaign.campaign_id}</span>}
        </header>
        {campaign ? <CampaignReadout summary={summary!} /> : <CampaignForm onCreated={onCreated} system={system} />}
      </section>
      <aside className="setup-side">
        <LeadsStep summary={summary} isDraft={isDraft} onChanged={onChanged} onStarted={onStarted} system={system} />
        <Readiness system={system} />
      </aside>
    </div>
  );
}

function CampaignForm({ onCreated, system }: { onCreated: (id: string) => void; system: SystemInfo | null }) {
  const [f, setF] = useState(INITIAL);
  const draftMode = system?.delivery.mode === "draft";
  const { busy, run } = useAction();
  const set = <K extends keyof typeof INITIAL>(k: K, v: (typeof INITIAL)[K]) => setF((prev) => ({ ...prev, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const immediate = draftMode || (f.single_recipient && f.send_now);  // mode draf tidak punya jadwal kirim
    const payload = { ...f, max_occurrences: f.cadence === "once" || f.single_recipient ? null : f.max_occurrences,
      send_now: immediate, schedule: immediate ? "" : f.schedule };
    const created = await run("create", () => api.createCampaign(payload),
      "Campaign dibuat. Lanjut muat lead.");
    if (created) onCreated(created.campaign_id);
  };

  return (
    <form onSubmit={submit} className="form">
      <fieldset>
        <legend>Penerima</legend>
        <div className="mode-choice" role="radiogroup" aria-label="Jumlah penerima">
          <label className={`mode ${f.single_recipient ? "is-on" : ""}`}>
            <input type="radio" name="mode" checked={f.single_recipient} onChange={() => set("single_recipient", true)} />
            <User size={18} aria-hidden />
            <span><strong>Satu orang</strong><small>{draftMode ? "Satu draf email untuk satu orang, dikunci sistem." : "Tepat 1 penerima, dikunci sistem. Cocok untuk kontak penting atau uji kirim."}</small></span>
          </label>
          <label className={`mode ${!f.single_recipient ? "is-on" : ""}`}>
            <input type="radio" name="mode" checked={!f.single_recipient} onChange={() => set("single_recipient", false)} />
            <Users size={18} aria-hidden />
            <span><strong>Banyak lead</strong><small>{draftMode ? "Impor CSV atau tambah beberapa lead; satu draf per lead." : "Impor CSV atau tambah beberapa lead; dikirim bertahap."}</small></span>
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Tujuan &amp; penawaran</legend>
        <div className="grid-2">
          <Field label="Nama campaign" span={2}><input required value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label="Tujuan" span={2}><input required value={f.goal} onChange={(e) => set("goal", e.target.value)} /></Field>
          <Field label="Penawaran" span={2}><textarea required rows={2} value={f.offer} onChange={(e) => set("offer", e.target.value)} /></Field>
          <Field label="Ajakan (CTA)" span={2}><input required value={f.cta} onChange={(e) => set("cta", e.target.value)} /></Field>
        </div>
      </fieldset>

      <fieldset>
        <legend>Personalisasi &amp; frekuensi</legend>
        <p className="legend-note">Dua pengaturan terpisah: seberapa personal isi email, dan seberapa sering campaign berulang.</p>
        <div className="grid-2">
          <Field label="Tingkat personalisasi">
            <select value={f.personalization} onChange={(e) => set("personalization", e.target.value)}>
              <option value="per_lead">Per lead (fakta spesifik, maks. {system?.limits.max_facts ?? 3})</option>
              <option value="segmen">Per segmen (industri/perusahaan)</option>
              <option value="template">Template tetap (tanpa LLM)</option>
            </select>
          </Field>
          {!f.single_recipient && (
            <Field label="Frekuensi">
              <select value={f.cadence} onChange={(e) => set("cadence", e.target.value)}>
                <option value="once">Sekali</option>
                <option value="weekly">Mingguan</option>
                <option value="monthly">Bulanan</option>
              </select>
            </Field>
          )}
          {!f.single_recipient && f.cadence !== "once" && (
            <Field label="Berhenti setelah" hint="Setiap kejadian membuat draft baru dan wajib disetujui ulang.">
              <input type="number" min={2} max={12} value={f.max_occurrences} onChange={(e) => set("max_occurrences", Number(e.target.value))} />
            </Field>
          )}
          {f.personalization === "template" && (
            <>
              <Field label="Subjek template" span={2} hint="Placeholder: {name}, {company}, {sender_name}, {cta}">
                <input required value={f.template_subject} onChange={(e) => set("template_subject", e.target.value)} />
              </Field>
              <Field label="Isi template" span={2}>
                <textarea required rows={5} value={f.template_body} onChange={(e) => set("template_body", e.target.value)} />
              </Field>
            </>
          )}
        </div>
      </fieldset>

      <fieldset>
        <legend>{draftMode ? "Pengirim & batas" : "Pengirim, jadwal & batas"}</legend>
        <div className="grid-2">
          <Field label="Nama pengirim" hint={draftMode ? "Dipakai sebagai penutup email." : system?.google.email ? `Dikirim dari ${system.google.email}` : "Akun Gmail belum dihubungkan (tab Koneksi)"}>
            <input required value={f.sender_name} onChange={(e) => set("sender_name", e.target.value)} />
          </Field>
          {f.single_recipient ? (draftMode ? null : (
            <Field label="Waktu kirim">
              <label className="consent">
                <input type="checkbox" checked={f.send_now} onChange={(e) => set("send_now", e.target.checked)} />
                <span>Kirim segera setelah draft disetujui</span>
              </label>
            </Field>
          )) : (
            <Field label="Jumlah lead" hint="Lead berlebih di CSV diabaikan; tidak ada penggantian diam-diam.">
              <input type="number" required min={1} max={1000} value={f.count} onChange={(e) => set("count", Number(e.target.value))} />
            </Field>
          )}
          {!draftMode && !(f.single_recipient && f.send_now) && (
            <Field label="Mulai jendela kirim" hint={f.single_recipient ? "Email dikirim pada atau setelah waktu ini, setelah disetujui." : "Email dikirim bertahap mulai waktu ini."}>
              <input type="datetime-local" required value={f.schedule} onChange={(e) => set("schedule", e.target.value)} />
            </Field>
          )}
          {!draftMode && <Field label="Zona waktu">
            <select value={f.timezone} onChange={(e) => set("timezone", e.target.value)}>
              <option value="Asia/Jakarta">WIB (Asia/Jakarta)</option>
              <option value="Asia/Makassar">WITA (Asia/Makassar)</option>
              <option value="Asia/Jayapura">WIT (Asia/Jayapura)</option>
            </select>
          </Field>}
          <Field label="Anggaran LLM (US$)" hint="Penulisan berhenti dan lead masuk review bila anggaran habis. 0 = tanpa batas.">
            <input type="number" min={0} step={0.5} value={f.budget} onChange={(e) => set("budget", Number(e.target.value))} />
          </Field>
        </div>
      </fieldset>

      <div className="form-actions">
        <Button variant="primary" type="submit" busy={busy === "create"}>Simpan campaign</Button>
      </div>
    </form>
  );
}

function CampaignReadout({ summary }: { summary: CampaignSummary }) {
  const c = summary.campaign;
  const rows: [string, string][] = [
    ["Tujuan", c.goal],
    ["Penawaran", c.offer],
    ["Ajakan", c.cta],
    ["Penerima", c.max_recipients ? `${c.max_recipients} orang (dikunci sistem)` : `Hingga ${c.count} lead`],
    ["Personalisasi", { per_lead: "Per lead", segmen: "Per segmen", template: "Template tetap" }[c.personalization]],
    ["Frekuensi", c.cadence === "once" ? "Sekali" : `${c.cadence === "weekly" ? "Mingguan" : "Bulanan"}, maks. ${c.max_occurrences} kali (kejadian ke-${c.current_occurrence})`],
    ["Pengirim", `${c.sender_name}${c.sender_email ? ` <${c.sender_email}>` : ""}`],
    ["Jendela kirim", `${fmtDate(c.schedule)} (${c.timezone})`],
    ["Anggaran LLM", c.budget ? `US$${c.budget}` : "Tanpa batas"],
  ];
  return (
    <>
      <dl className="readout">
        {rows.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>
      <p className="muted small">Konfigurasi dikunci setelah dibuat karena approval terikat pada konfigurasi ini. Buat campaign baru untuk perubahan.</p>
    </>
  );
}

function LeadsStep({ summary, isDraft, onChanged, onStarted, system }: {
  summary: CampaignSummary | null; isDraft: boolean; onChanged: () => void; onStarted: () => void; system: SystemInfo | null;
}) {
  const file = useRef<HTMLInputElement>(null);
  const { busy, run } = useAction();
  const toast = useToast();
  const campaign = summary?.campaign;
  const counts = summary?.counts;
  const leads = usePoll(campaign && isDraft ? () => api.leads(campaign.campaign_id) : null, 4000, [campaign?.campaign_id, isDraft]);

  if (!campaign) {
    return (
      <section className="panel step-card is-waiting">
        <h3>Lead</h3>
        <p className="muted">Simpan campaign dahulu, lalu muat lead dari CSV atau data fiktif.</p>
      </section>
    );
  }
  const id = campaign.campaign_id;
  const upload = async (f: File | undefined) => {
    if (!f) return;
    const r = await run("upload", () => api.uploadLeads(id, f), (x) => `${x.added} lead diimpor (total ${x.total}/${x.requested}).`);
    if (file.current) file.current.value = "";
    if (r?.skipped.length) toast(`${r.skipped.length} baris dilewati: ${r.skipped.slice(0, 3).join("; ")}`, "error");
    changed();
  };
  const missingLive = system?.integrations.filter((i) => i.mode === "belum" && i.name !== "gmail") ?? [];
  const changed = () => { onChanged(); leads.refresh(); };

  return (
    <section className="panel step-card">
      <h3>Lead</h3>
      <p className="lead-count">
        <span className="num">{counts?.imported ?? 0}</span> dari <span className="num">{counts?.requested ?? campaign.count}</span> lead dimuat
      </p>
      {isDraft && campaign.max_recipients === 1 ? (
        <>
          <LeadPreviewList leads={leads.data ?? []} />
          {(counts?.imported ?? 0) < 1 ? <ManualLeadForm campaignId={id} onAdded={changed} /> : (
            <p className="field-hint">Campaign satu penerima sudah berisi 1 orang. Periksa datanya, lalu jalankan agen.</p>
          )}
          <Button variant="primary" icon={<Play size={16} />} busy={busy === "run"} disabled={!counts?.imported}
            onClick={async () => { const r = await run("run", () => api.run(id), "Agen mulai menyiapkan email untuk 1 penerima."); if (r) onStarted(); }}>
            Jalankan agen
          </Button>
        </>
      ) : isDraft ? (
        <>
          <div className="stack">
            <input ref={file} type="file" accept=".csv,text/csv" hidden onChange={(e) => upload(e.target.files?.[0])} />
            <Button icon={<FileUp size={16} />} busy={busy === "upload"} onClick={() => file.current?.click()}>Unggah CSV</Button>
            <Button icon={<Sparkles size={16} />} busy={busy === "sample"}
              onClick={async () => { await run("sample", () => api.sampleLeads(id), (x) => `${x.added} lead fiktif dimuat.`); changed(); }}>
              Muat 100 lead fiktif
            </Button>
          </div>
          <LeadPreviewList leads={leads.data ?? []} />
          <ManualLeadForm campaignId={id} onAdded={changed} />
          <p className="field-hint">
            Kolom CSV: <code>name</code> dan <code>company</code> atau <code>description</code> (wajib), <code>email, domain, title_hint, linkedin_url, permission_status, permission_ref, crm_id</code>.
            Hanya <code>permission_status=granted</code> yang dapat dikirimi. Enrichment Apify hanya berjalan untuk lead yang punya <code>linkedin_url</code>.
          </p>
          {missingLive.length > 0 && (
            <Notice tone="warn" title="Belum semua layanan siap">
              {missingLive.map((i) => i.name).join(", ")} belum dikonfigurasi. Lead tetap diproses, tapi tahap terkait masuk review.
            </Notice>
          )}
          <Button variant="primary" icon={<Play size={16} />} busy={busy === "run"} disabled={!counts?.imported}
            onClick={async () => { const r = await run("run", () => api.run(id), (x) => `Agen mulai memproses ${x.leads} lead.`); if (r) onStarted(); }}>
            Jalankan agen
          </Button>
        </>
      ) : (
        <p className="muted">Campaign sedang berjalan ({campaign.status}). Tinjau hasilnya di Preview &amp; Approval.</p>
      )}
    </section>
  );
}

function Readiness({ system }: { system: SystemInfo | null }) {
  if (!system) return null;
  const label = { live: "Siap", simulasi: "Simulasi", belum: "Belum", lokal: "Lokal" } as const;
  const draftMode = system.delivery.mode === "draft";
  return (
    <section className="panel step-card">
      <h3>Kesiapan layanan</h3>
      <ul className="readiness">
        {system.integrations.filter((i) => !(draftMode && i.name === "gmail")).map((i) => (
          <li key={i.name}>
            <span className={`dot dot-${i.mode}`} aria-hidden />
            <span className="readiness-name">{i.purpose}</span>
            <span className={`readiness-state state-${i.mode}`}>{label[i.mode]}</span>
          </li>
        ))}
        {draftMode ? (
          <li>
            <span className="dot dot-lokal" aria-hidden />
            <span className="readiness-name">Pengiriman email</span>
            <span className="readiness-state state-lokal">Opsional</span>
          </li>
        ) : (
          <li>
            <span className={`dot dot-${system.google.connected ? "live" : "belum"}`} aria-hidden />
            <span className="readiness-name">Akun Gmail pengirim</span>
            <span className={`readiness-state state-${system.google.connected ? "live" : "belum"}`}>{system.google.connected ? "Terhubung" : "Belum"}</span>
          </li>
        )}
      </ul>
      {draftMode
        ? <p className="field-hint">Mode draf: keluaran berupa isi email yang bisa disalin atau diunduh. Pengiriman langsung aktif setelah Google Client ID/Secret diisi (tab Koneksi).</p>
        : system.sending.blocked_reason && <p className="field-hint">Pengiriman ditahan: {system.sending.blocked_reason}.</p>}
    </section>
  );
}
