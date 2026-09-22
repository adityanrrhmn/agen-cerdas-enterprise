import { useState } from "react";
import { Link2, Link2Off, PlugZap } from "lucide-react";
import { api, type SystemInfo } from "../api";
import { Button, Notice, fmtDate, useAction } from "../ui";

const MODE = { live: "Terkonfigurasi", simulasi: "Simulasi (data fiktif)", belum: "Belum dikonfigurasi", lokal: "File lokal" } as const;

export default function Connections({ system, onChanged, googleResult }: {
  system: SystemInfo; onChanged: () => void; googleResult: { status: string; detail: string } | null;
}) {
  const { busy, run } = useAction();
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const g = system.google;

  return (
    <div className="connections">
      {googleResult?.status === "connected" && <Notice title="Akun Google terhubung">Email akan dikirim dari {g.email || "akun yang login"}.</Notice>}
      {googleResult?.status === "error" && <Notice tone="error" title="Gagal menghubungkan akun Google">{googleResult.detail}</Notice>}

      {system.delivery.mode === "draft" && (
        <section className="panel draft-explain">
          <header className="panel-head"><h2>Mode draf aktif</h2><span className="muted small">{system.delivery.reason}</span></header>
          <div className="draft-explain-body">
            <p>Semua agen tetap bekerja (enrichment, riset bukti, penulisan, pemeriksaan keamanan). Hasil akhirnya adalah
              <strong> isi email</strong> yang bisa difinalkan, disalin, atau diunduh sebagai .eml/CSV. Aplikasi tidak mengirim email.</p>
            <p className="muted small">Untuk mengirim langsung dari aplikasi: isi <code>GOOGLE_CLIENT_ID</code> dan <code>GOOGLE_CLIENT_SECRET</code> di
              .env, restart backend, lalu hubungkan akun Google di bawah. Mode juga bisa dipaksa dengan <code>DELIVERY_MODE=draft</code>.</p>
          </div>
        </section>
      )}

      <section className="panel google">
        <header className="panel-head"><h2>Akun Gmail pengirim{system.delivery.mode === "draft" ? " (opsional)" : ""}</h2></header>
        {g.connected ? (
          <div className="google-row">
            <div>
              <p className="google-email">{g.email}</p>
              <p className="muted small">Terhubung {g.connected_at ? fmtDate(g.connected_at) : ""} · izin: kirim email saja (tidak membaca kotak masuk)</p>
            </div>
            <Button variant="ghost" icon={<Link2Off size={15} />} busy={busy === "disc"}
              onClick={async () => { await run("disc", () => api.disconnectGoogle(), "Akun Google diputus dan token dicabut."); onChanged(); }}>
              Putuskan
            </Button>
          </div>
        ) : (
          <div className="google-row">
            <div>
              <p>Hubungkan akun yang akan menjadi pengirim. Google meminta izin <strong>kirim email</strong>; aplikasi tidak dapat membaca email Anda.</p>
              {!g.configured && <p className="warn-text small">Isi GOOGLE_CLIENT_ID dan GOOGLE_CLIENT_SECRET di .env lalu restart backend.</p>}
            </div>
            <a className={`btn btn-primary btn-md ${g.configured ? "" : "is-disabled"}`} href={g.configured ? g.connect_url : undefined} aria-disabled={!g.configured}>
              <Link2 size={16} aria-hidden /><span>Hubungkan akun Google</span>
            </a>
          </div>
        )}
        {system.delivery.mode !== "draft" && <dl className="readout compact">
          <div><dt>Pengiriman</dt><dd>{system.sending.enabled ? "Aktif" : "Nonaktif"} (GMAIL_SEND_ENABLED){system.sending.blocked_reason ? ` · ditahan: ${system.sending.blocked_reason}` : ""}</dd></div>
          <div><dt>Allowlist penerima</dt><dd>{system.sending.allowlist.length ? system.sending.allowlist.join(", ") : "kosong: tidak ada email yang akan dikirim"}</dd></div>
          <div><dt>Jeda antar-email</dt><dd>{system.sending.interval_seconds} detik</dd></div>
          <div><dt>Redirect OAuth</dt><dd className="mono">{g.redirect_uri}</dd></div>
        </dl>}
      </section>

      <section className="panel">
        <header className="panel-head"><h2>Layanan</h2><span className="muted small">Key dibaca dari .env; nilainya tidak pernah ditampilkan.</span></header>
        <table className="table">
          <thead><tr><th>Layanan</th><th>Status</th><th>Keterangan</th><th /></tr></thead>
          <tbody>
            {system.integrations.map((i) => {
              const r = results[i.name];
              return (
                <tr key={i.name}>
                  <td><strong className="cap">{i.name}</strong><span className="cell-sub">{i.purpose}</span></td>
                  <td>{system.delivery.mode === "draft" && i.name === "gmail" && i.mode === "belum"
                    ? <span className="readiness-state state-lokal">Opsional (mode draf)</span>
                    : <span className={`readiness-state state-${i.mode}`}>{MODE[i.mode]}</span>}</td>
                  <td>
                    {i.missing.length > 0 && <span className="cell-sub">Kurang: <code>{i.missing.join(", ")}</code></span>}
                    {i.name === "openrouter" && <span className="cell-sub">Model: {system.model}</span>}
                    {i.name === "sheets" && (
                      <span className="cell-sub">
                        {system.storage.note}
                        {system.storage.service_account_email && <> · share spreadsheet ke <code>{system.storage.service_account_email}</code></>}
                        {system.storage.last_flush_error && <span className="warn-text"> · galat tulis: {system.storage.last_flush_error}</span>}
                      </span>
                    )}
                    {r && <span className={`cell-sub ${r.ok ? "ok-text" : "warn-text"}`}>{r.ok ? "Berhasil" : "Gagal"}: {r.message}</span>}
                  </td>
                  <td>
                    <Button size="sm" icon={<PlugZap size={14} />} busy={busy === i.name} disabled={i.mode === "belum"}
                      onClick={async () => {
                        const res = await run(i.name, () => api.testIntegration(i.name));
                        if (res) setResults((prev) => ({ ...prev, [i.name]: res }));
                      }}>
                      Tes
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="muted small">Tes memakai endpoint tanpa biaya (validasi key, info akun, atau metadata spreadsheet); tidak menjalankan actor, pencarian, atau mengirim email.</p>
      </section>

      <section className="panel">
        <header className="panel-head"><h2>Batas agen</h2></header>
        <dl className="readout compact">
          <div><dt>Worker paralel</dt><dd>{system.limits.workers} (runtime A + B)</dd></div>
          <div><dt>Batch</dt><dd>{system.limits.batch_size} lead</dd></div>
          <div><dt>Fakta per draft</dt><dd>maks. {system.limits.max_facts}</dd></div>
          <div><dt>Revisi otomatis</dt><dd>maks. {system.limits.max_revisions}</dd></div>
          <div><dt>Entity linking</dt><dd>S ≥ {system.limits.entity_threshold.toLocaleString("id-ID")} dan selisih ≥ {system.limits.entity_gap.toLocaleString("id-ID")}</dd></div>
        </dl>
      </section>
    </div>
  );
}
