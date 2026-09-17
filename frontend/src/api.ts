export type Decision = "PASS" | "REVIEW" | "BLOCK" | "";

export interface Reason {
  level: "block" | "review" | "info";
  code: string;
  message: string;
}

export interface Campaign {
  campaign_id: string;
  name: string;
  goal: string;
  offer: string;
  cta: string;
  personalization: "template" | "segmen" | "per_lead";
  cadence: "once" | "weekly" | "monthly";
  max_occurrences: number;
  count: number;
  max_recipients: number;
  timezone: string;
  schedule: string;
  budget: number;
  sender_name: string;
  sender_email: string;
  status: "DRAFT" | "RUNNING" | "PAUSED" | "COMPLETED";
  current_occurrence: number;
  created_at: string;
}

export interface CampaignSummary {
  campaign: Campaign;
  occurrence_id: string;
  counts: { requested: number; imported: number; tasks: number; in_progress: number; pass: number; review: number; block: number };
  email_status: Record<string, number>;
  stages: Record<string, number>;
  cost_usd: number;
  prep_seconds: { avg: number | null; p95: number | null; n: number };
}

export interface LeadRow {
  lead_id: string;
  name: string;
  description: string;
  company: string;
  email: string;
  stage: string;
  decision: Decision;
  match_score: number | null;
  reasons: Reason[];
  subject: string;
  email_status: string;
  send_key: string;
  task_status: string;
  host: string;
}

export interface Candidate {
  name: string;
  title: string;
  company: string;
  domain: string;
  industry: string;
  location: string;
  profile_url: string;
  score: { d: number; n: number; c: number; r: number; S: number };
}

export interface Evidence {
  fact_id: string;
  field: string;
  value: string;
  source_url: string;
  retrieved_at: string;
  match_score: number | null;
  source_type: "crm" | "apify" | "firecrawl";
  quote: string;
  selected: boolean;
}

export interface Email {
  send_key: string;
  occurrence_id: string;
  to_email: string;
  subject: string;
  body: string;
  used_fact_ids: string[];
  warnings: string[];
  draft_version: number;
  security_decision: Decision;
  security_reasons: Reason[];
  approval_hash: string;
  approved_at: string | null;
  schedule: string;
  gmail_id: string;
  status: string;
  error: string;
  llm_model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface Task {
  task_id: string;
  stage: string;
  status: string;
  host: string;
  generation: number;
  retry: number;
  checkpoint: { done?: string[]; link?: string };
  error: string;
}

export interface LeadDetail {
  lead: LeadRow & {
    domain: string; title_hint: string; linkedin_url: string; permission_status: string; permission_ref: string;
    candidates: Candidate[]; identity: Candidate | null;
    hints: { organization: string; organization_aliases: string[]; role: string; location: string } | null;
  };
  task: Task | null;
  email: Email | null;
  evidence: Evidence[];
  audit: { event_id: string; actor: string; timestamp: string; change_summary: string }[];
}

export interface Integration {
  name: "openrouter" | "apify" | "firecrawl" | "sheets" | "gmail";
  purpose: string;
  mode: "live" | "simulasi" | "belum" | "lokal";
  missing: string[];
}

export interface SystemInfo {
  storage: { backend: string; note: string; pending_writes: number; last_flush_error: string | null; service_account_email: string };
  google: { configured: boolean; connected: boolean; email: string; connected_at?: string; connect_url: string; redirect_uri: string };
  integrations: Integration[];
  model: string;
  sending: { enabled: boolean; blocked_reason: string | null; allowlist: string[]; interval_seconds: number; sender: string };
  limits: { batch_size: number; workers: number; max_facts: number; max_revisions: number; entity_threshold: number; entity_gap: number };
  simulate: boolean;
}

export interface RuntimeTask {
  task_id: string;
  lead_id: string;
  stage: string;
  status: string;
  generation: number;
  agent_id: string;
  active: boolean;
}

export interface RuntimeInfo {
  name: "A" | "B";
  online: boolean;
  capacity: number;
  active: number;
  queued: number;
  completed: number;
  avg_seconds: number;
  tasks: RuntimeTask[];
}

export interface Migration {
  task_id: string;
  lead_id: string;
  from: string;
  to: string;
  generation: number;
  checkpoint: string[];
  reason: string;
  at: string;
  overhead_ms: number;
}

export interface Metrics {
  api_calls: Record<string, number>;
  api_errors: Record<string, number>;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  messages: number;
  performatives: Record<string, number>;
  migrations: number;
  incidents: number;
}

export interface QueueRow {
  send_key: string;
  lead_id: string;
  occurrence_id: string;
  to_email: string;
  subject: string;
  schedule: string;
  status: string;
  gmail_id: string;
  error: string;
}

export interface AgentEvent {
  id: number;
  ts: string;
  type: "message" | "stage" | "lead" | "migration" | "incident" | "send" | "approval" | "runtime";
  text: string;
  performative?: string;
  sender?: string;
  receiver?: string;
  lead_id?: string;
  task_id?: string;
  lease_generation?: number;
}

export interface ManualLead {
  name: string;
  description: string;
  email: string;
  company: string;
  linkedin_url: string;
  permission_granted: boolean;
  permission_ref: string;
}

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("Backend tidak dapat dihubungi. Pastikan server berjalan di port 8000.");
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Permintaan gagal (HTTP ${res.status})`);
  }
  return data as T;
}

const enc = encodeURIComponent;

export const api = {
  system: () => request<SystemInfo>("GET", "/system"),
  testIntegration: (name: string) => request<{ ok: boolean; message: string }>("POST", `/integrations/${name}/test`),
  disconnectGoogle: () => request("POST", "/google/disconnect"),
  campaigns: () => request<CampaignSummary[]>("GET", "/campaigns"),
  campaign: (id: string) => request<CampaignSummary>("GET", `/campaigns/${enc(id)}`),
  createCampaign: (data: Record<string, unknown>) => request<Campaign>("POST", "/campaigns", data),
  uploadLeads: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ added: number; skipped: string[]; total: number; requested: number }>("POST", `/campaigns/${enc(id)}/leads/csv`, form);
  },
  addLead: (id: string, data: ManualLead) => request<LeadRow>("POST", `/campaigns/${enc(id)}/leads`, data),
  setLeadEmail: (leadId: string, email: string) => request("PUT", `/leads/${enc(leadId)}/email`, { email }),
  sampleLeads: (id: string) => request<{ added: number; total: number; requested: number; skipped: string[] }>("POST", `/campaigns/${enc(id)}/leads/sample`),
  run: (id: string) => request<{ leads: number }>("POST", `/campaigns/${enc(id)}/run`),
  pause: (id: string, paused: boolean) => request("POST", `/campaigns/${enc(id)}/pause`, { paused }),
  approvePass: (id: string) => request<{ approved: number }>("POST", `/campaigns/${enc(id)}/approve-pass`),
  leads: (id: string) => request<LeadRow[]>("GET", `/campaigns/${enc(id)}/leads`),
  lead: (leadId: string) => request<LeadDetail>("GET", `/leads/${enc(leadId)}`),
  resolve: (leadId: string, candidate_index: number | null) => request("POST", `/leads/${enc(leadId)}/resolve`, { candidate_index }),
  suppress: (email: string, reason: string) => request("POST", "/suppression", { email, reason }),
  editEmail: (key: string, subject: string, body: string) => request<Email>("PUT", `/emails/${enc(key)}`, { subject, body }),
  approve: (key: string, draft_version: number, acknowledge_review: boolean) =>
    request<Email>("POST", `/emails/${enc(key)}/approve`, { draft_version, acknowledge_review }),
  reject: (key: string) => request("POST", `/emails/${enc(key)}/reject`),
  reconcile: (key: string, outcome: "sent" | "not_sent") => request("POST", `/emails/${enc(key)}/reconcile`, { outcome }),
  queue: (id: string) => request<QueueRow[]>("GET", `/campaigns/${enc(id)}/emails`),
  runtimes: () => request<{ runtimes: RuntimeInfo[]; migrations: Migration[] }>("GET", "/runtimes"),
  setOnline: (name: string, online: boolean) => request<{ moved: number }>("POST", `/runtimes/${name}/online`, { online }),
  migrate: (taskId: string, target: string) => request<Migration>("POST", `/tasks/${enc(taskId)}/migrate`, { target }),
  metrics: () => request<Metrics>("GET", "/metrics"),
  recentEvents: () => request<AgentEvent[]>("GET", "/events/recent?limit=200"),
};
