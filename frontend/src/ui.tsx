import { type ButtonHTMLAttributes, type ReactNode, createContext, useCallback, useContext, useState } from "react";
import {
  AlertTriangle, Ban, CheckCircle2, CircleDashed, Clock3, HelpCircle, Loader2, MailCheck, MailX, Send, ShieldCheck, XCircle,
} from "lucide-react";

// ---------------------------------------------------------------- format
const dateFmt = new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Jakarta" });
const timeFmt = new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Jakarta" });

export const fmtDate = (iso?: string | null) => (iso ? `${dateFmt.format(new Date(iso))} WIB` : "–");
export const fmtTime = (iso?: string | null) => (iso ? timeFmt.format(new Date(iso)) : "–");
export const fmtNum = (n: number | null | undefined, digits = 0) =>
  n === null || n === undefined ? "–" : n.toLocaleString("id-ID", { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const fmtUsd = (n: number) => `US$${n.toLocaleString("id-ID", { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`;

// ---------------------------------------------------------------- status
type Tone = "pass" | "review" | "block" | "neutral" | "info" | "done";

const STATUS: Record<string, { label: string; tone: Tone; icon: typeof CheckCircle2 }> = {
  PASS: { label: "Lolos", tone: "pass", icon: ShieldCheck },
  REVIEW: { label: "Perlu review", tone: "review", icon: AlertTriangle },
  BLOCK: { label: "Diblokir", tone: "block", icon: Ban },
  AWAITING_APPROVAL: { label: "Siap disetujui", tone: "pass", icon: ShieldCheck },
  NEEDS_REVIEW: { label: "Perlu review", tone: "review", icon: AlertTriangle },
  NEEDS_IDENTITY: { label: "Identitas ambigu", tone: "review", icon: HelpCircle },
  BLOCKED: { label: "Diblokir", tone: "block", icon: Ban },
  APPROVED: { label: "Disetujui, antre", tone: "info", icon: Clock3 },
  SENDING: { label: "Mengirim", tone: "info", icon: Send },
  SENT: { label: "Diterima Gmail", tone: "done", icon: MailCheck },
  SENT_UNKNOWN: { label: "Status tak pasti", tone: "review", icon: HelpCircle },
  FAILED: { label: "Gagal kirim", tone: "block", icon: MailX },
  REJECTED: { label: "Ditolak", tone: "neutral", icon: XCircle },
  NEEDS_REAPPROVAL: { label: "Perlu approval ulang", tone: "review", icon: AlertTriangle },
  NOT_SENT: { label: "Tidak terkirim", tone: "neutral", icon: MailX },
};

export function StatusBadge({ status, fallback }: { status: string; fallback?: string }) {
  const s = STATUS[status];
  if (!s) {
    return (
      <span className="badge tone-neutral">
        <CircleDashed size={13} aria-hidden /> {fallback ?? (status || "Diproses")}
      </span>
    );
  }
  const Icon = s.icon;
  return (
    <span className={`badge tone-${s.tone}`}>
      <Icon size={13} aria-hidden /> {s.label}
    </span>
  );
}

export const STAGE_LABEL: Record<string, string> = {
  imported: "Diimpor", queued: "Antre", validated: "Divalidasi", enrichment: "Enrichment", enriched: "Enrichment selesai",
  research: "Riset bukti", writing: "Menulis draft", decided: "Diputuskan", blocked: "Diblokir",
  identity_review: "Review identitas", identity_resolved: "Identitas dipilih", failed: "Gagal", no_runtime: "Tanpa runtime",
  validate: "Validasi", security: "Pemeriksaan",
};

// ---------------------------------------------------------------- kontrol
interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  busy?: boolean;
  icon?: ReactNode;
  size?: "md" | "sm";
}

export function Button({ variant = "secondary", busy, icon, size = "md", children, disabled, className = "", ...rest }: BtnProps) {
  return (
    <button className={`btn btn-${variant} btn-${size} ${className}`} disabled={disabled || busy} aria-busy={busy} {...rest}>
      {busy ? <Loader2 size={15} className="spin" aria-hidden /> : icon}
      {children && <span>{children}</span>}
    </button>
  );
}

export function Field({ label, hint, children, span }: { label: string; hint?: ReactNode; children: ReactNode; span?: 2 }) {
  return (
    <label className={`field ${span === 2 ? "span-2" : ""}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {children && <div className="empty-body">{children}</div>}
      {action}
    </div>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "error"; title?: string; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : "status"}>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------- toast
interface Toast { id: number; text: string; tone: "ok" | "error" }
const ToastCtx = createContext<(text: string, tone?: "ok" | "error") => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { id, text, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

/** Jalankan aksi async dengan status sibuk dan toast galat. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const run = useCallback(
    async <T,>(key: string, fn: () => Promise<T>, success?: string | ((r: T) => string)) => {
      setBusy(key);
      try {
        const result = await fn();
        if (success) toast(typeof success === "function" ? success(result) : success);
        return result;
      } catch (e) {
        toast((e as Error).message, "error");
        return undefined;
      } finally {
        setBusy(null);
      }
    },
    [toast],
  );
  return { busy, run };
}
