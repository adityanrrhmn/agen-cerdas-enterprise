import { useState } from "react";
import { UserPlus } from "lucide-react";
import { api, type LeadRow, type ManualLead } from "../api";
import { Button, Field, useAction } from "../ui";

const EMPTY: ManualLead = { name: "", description: "", email: "", company: "", linkedin_url: "", permission_granted: false, permission_ref: "" };

/** Form lead manual: cukup nama lengkap dan deskripsi; agen menyimpulkan instansi dan peran dari deskripsi. */
export function ManualLeadForm({ campaignId, onAdded }: { campaignId: string; onAdded: () => void }) {
  const [f, setF] = useState<ManualLead>(EMPTY);
  const [more, setMore] = useState(false);
  const { busy, run } = useAction();
  const set = <K extends keyof ManualLead>(k: K, v: ManualLead[K]) => setF((p) => ({ ...p, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const lead = await run("add", () => api.addLead(campaignId, f), (l) => `${l.name} ditambahkan.`);
    if (lead) {
      setF(EMPTY);
      onAdded();
    }
  };

  return (
    <form className="manual-lead" onSubmit={submit}>
      <h4>Tambah lead manual</h4>
      <Field label="Nama lengkap">
        <input required minLength={2} value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="Azhari" />
      </Field>
      <Field label="Deskripsi" hint="Peran dan instansi. Agen memakai ini untuk mencari bukti tentang orang yang tepat.">
        <textarea required minLength={5} rows={3} value={f.description} onChange={(e) => set("description", e.target.value)}
          placeholder="Dosen di UGM serta guru besar di sana" />
      </Field>
      <Field label="Email" hint="Boleh diisi nanti; draft tidak dapat disetujui sebelum email ada.">
        <input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} placeholder="nama@instansi.ac.id" />
      </Field>
      {more ? (
        <>
          <Field label="Instansi / perusahaan" hint="Kosongkan bila sudah jelas dari deskripsi.">
            <input value={f.company} onChange={(e) => set("company", e.target.value)} />
          </Field>
          <Field label="URL LinkedIn" hint="Mengaktifkan enrichment Apify dan verifikasi identitas.">
            <input type="url" value={f.linkedin_url} onChange={(e) => set("linkedin_url", e.target.value)} placeholder="https://www.linkedin.com/in/..." />
          </Field>
        </>
      ) : (
        <button type="button" className="link-more" onClick={() => setMore(true)}>+ Instansi dan URL LinkedIn (opsional)</button>
      )}
      <label className="consent">
        <input type="checkbox" checked={f.permission_granted} onChange={(e) => set("permission_granted", e.target.checked)} />
        <span>Orang ini sudah memberi izin untuk dihubungi. Tanpa ini, lead akan diblokir.</span>
      </label>
      {f.permission_granted && (
        <Field label="Dasar izin" hint="Contoh: kartu nama di seminar 12 Sep 2026, formulir webinar.">
          <input value={f.permission_ref} onChange={(e) => set("permission_ref", e.target.value)} />
        </Field>
      )}
      <Button type="submit" icon={<UserPlus size={16} />} busy={busy === "add"}>Tambahkan lead</Button>
    </form>
  );
}

export function LeadPreviewList({ leads }: { leads: LeadRow[] }) {
  if (!leads.length) return null;
  const shown = leads.slice(-6).reverse();
  return (
    <ul className="lead-preview" aria-label="Lead terakhir dimuat">
      {shown.map((l) => (
        <li key={l.lead_id}>
          <strong>{l.name}</strong>
          <span>{l.description || l.company}</span>
          {!l.email && <em>tanpa email</em>}
        </li>
      ))}
      {leads.length > shown.length && <li className="muted small">+{leads.length - shown.length} lead lain</li>}
    </ul>
  );
}
