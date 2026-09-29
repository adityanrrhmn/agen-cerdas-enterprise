import type { AgentEvent, CampaignSummary, LeadRow } from "../api";

export const AGENTS = [
  { id: "orchestrator", name: "Orchestrator", job: "Membagi pekerjaan dan mengatur urutan agen.", verb: "Mengatur task", color: "#297c79", hue: "0deg" },
  { id: "enrichment", name: "Enrichment", job: "Mencocokkan identitas dan melengkapi profil lead.", verb: "Mencocokkan profil", color: "#356baa", hue: "45deg" },
  { id: "research", name: "Research", job: "Mencari sumber dan memilih fakta yang dapat ditelusuri.", verb: "Mencari bukti", color: "#8a5b9a", hue: "110deg" },
  { id: "writer", name: "Writer", job: "Menyusun email personal berdasarkan fakta terpilih.", verb: "Menulis draf", color: "#986b2c", hue: "205deg" },
  { id: "security", name: "Security", job: "Memeriksa izin, fakta, dan keamanan draf. Persetujuan tetap oleh manusia.", verb: "Memeriksa draf", color: "#497345", hue: "300deg" },
] as const;
export type AgentId = typeof AGENTS[number]["id"];
export type OfficeState = { mode: "idle" | "working" | "recent" | "review" | "done" | "paused" | "unknown"; label: string };
export type OfficeStates = Record<AgentId, OfficeState>;

/** Lead stage is current work; task checkpoint stages are not activity signals. */
export function officeStates(summary: CampaignSummary, leads: LeadRow[] | null, events: AgentEvent[], now: number, unavailable = false): OfficeStates {
  const state = Object.fromEntries(AGENTS.map(a => [a.id, { mode: "idle", label: "Siap menerima tugas" }])) as OfficeStates;
  if (unavailable || leads === null) {
    for (const a of AGENTS) state[a.id] = { mode: "unknown", label: unavailable ? "Status tidak tersedia" : "Memuat status" };
    return state;
  }
  if (summary.campaign.status === "PAUSED") {
    for (const a of AGENTS) state[a.id] = { mode: "paused", label: "Campaign dijeda" };
    return state;
  }
  if (summary.campaign.status === "DRAFT") return state;
  const active = leads.filter(l => l.task_status === "RUNNING");
  const mapping: Record<AgentId, string[]> = {
    orchestrator: ["queued", "validated", "identity_resolved"], enrichment: ["enrichment"],
    research: ["research"], writer: ["writing"], security: ["validate", "security"],
  };
  for (const a of AGENTS) {
    const n = active.filter(l => mapping[a.id].includes(l.stage)).length;
    if (n) state[a.id] = { mode: "working", label: `${a.verb} · ${n} lead` };
  }
  if (active.length) state.orchestrator = { mode: "working", label: `Mengatur ${active.length} task` };
  // Security is synchronous: show a short, explicitly recent activity acknowledgement.
  const ids = new Set(leads.map(l => l.lead_id));
  const recent = events.some(e => e.sender === "security" && e.lead_id && ids.has(e.lead_id)
    && ["PASS", "REVIEW", "BLOCK"].includes(e.performative ?? "")
    && now - Date.parse(e.ts) >= 0 && now - Date.parse(e.ts) < 4000);
  if (recent) state.security = { mode: "recent", label: "Baru memeriksa hasil" };
  else if (leads.some(l => l.email_status === "NEEDS_REVIEW" || l.email_status === "AWAITING_APPROVAL" || l.task_status === "WAITING_REVIEW")) {
    state.security = { mode: "review", label: "Menunggu review manusia" };
  } else if (summary.counts.pass + summary.counts.review + summary.counts.block > 0) {
    state.security = { mode: "done", label: "Hasil pemeriksaan tersedia" };
  }
  if (summary.campaign.status === "COMPLETED") {
    for (const a of AGENTS) state[a.id] = { mode: "done", label: "Campaign selesai" };
  }
  if (leads.some(l => l.task_status === "HELD")) state.orchestrator = { mode: "review", label: "Task tertahan · cek runtime" };
  return state;
}
