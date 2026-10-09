// Skill Observatory API entity types.
// Mirrors .local/receipts/ui-contract.txt and the live root ledger shapes;
// optional fields tolerate backend growth without UI changes.

export type Locale = "zh-CN" | "en";

export interface Settings {
  locale: Locale;
  timezone: string;
  paused: boolean;
  automatic_review?: boolean;
  auto_promote?: boolean;
  scopes?: string[];
  [key: string]: unknown;
}

export interface Skill {
  id: string;
  name: string;
  owner?: string | null;
  source?: string | null;
  status?: string; // observing | ...
  score?: number | null;
  auto_promote?: boolean;
  created_at?: string;
  package_sha256?: string | null;
  path?: string;
  license?: string | null;
  missing?: string[];
  manifest?: { files?: Record<string, string>; package_sha256?: string };
  [key: string]: unknown;
}

export interface Run {
  id: string;
  created_at: string;
  updated_at?: string;
  status: string; // triaged | observed | evidence_pending | ready | reviewed
  outcome?: string; // unverified | partial | succeeded | failed | interrupted ...
  origin?: string;
  session_id?: string | null;
  turn_id?: string | null;
  agent_id?: string | null;
  skill_id?: string | null;
  skill_name?: string | null;
  last_event?: string;
  event_ids?: string[];
  attributions?: unknown[];
  missing?: string[];
  input?: string;
  job_id?: string;
  environment_id?: string;
  details?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface Review {
  id?: string;
  review_id?: string;
  run_id: string;
  skill_id?: string | null;
  created_at: string;
  status?: string; // triaged | ...
  decision?: string; // HOLD | NO_CHANGE | CHANGE_PROPOSED | ...
  verdict?: string;
  reason_code?: string;
  missing?: string[];
  findings?: unknown[];
  attribution?: string;
  coverage?: { outcome?: string; tools?: string | Record<string, unknown>; [k: string]: unknown };
  outcome?: { source?: string; status?: string; [k: string]: unknown };
  reviewer_version?: string;
  evidence_manifest_sha256?: string;
  schema_version?: number;
  summary?: string;
  [key: string]: unknown;
}

export interface Experiment {
  id: string;
  skill_id?: string;
  skill_name?: string;
  parent_version?: string;
  candidate_version?: string;
  protocol?: string;
  frozen_config?: Record<string, unknown>;
  budget?: Record<string, number>;
  cost?: { value: number; unit?: string };
  status: string;
  verdict?: string;
  reason_code?: string;
  stages?: { stage: string; at?: string; completed?: boolean; note?: string }[];
  installation_id?: string;
  created_at: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface Installation {
  id: string;
  experiment_id?: string;
  skill_id?: string;
  skill_name?: string;
  status: string;
  disk_version?: string;
  loaded_version?: string;
  created_at?: string;
  updated_at?: string;
  reason_code?: string;
  [key: string]: unknown;
}

export interface Job {
  id: string;
  run_id?: string;
  kind?: string;
  status: string; // hold | queued | running | completed | failed | cancelled | waiting
  intent?: string;
  lease_until?: number;
  attempts?: number;
  reason_code?: string;
  message?: string;
  created_at: string;
  updated_at?: string;
  finished_at?: string;
  receipt_id?: string;
  progress?: { stage?: string; completed?: string[]; current?: string; note?: string };
  [key: string]: unknown;
}

export interface Environment {
  id: string;
  name?: string;
  profile?: string;
  status?: string; // checking | passed | failed | unknown | available ...
  available?: boolean;
  canary_status?: string;
  last_checked_at?: string;
  created_at?: string;
  image_digest?: string;
  network?: string; // none | allowed ...
  secrets?: string;
  host_mounts?: string[];
  writable_roots?: string[];
  tools?: { name: string; granted?: boolean; schema?: string }[];
  mcp_profiles?: { name: string; access?: string }[];
  reason_code?: string;
  [key: string]: unknown;
}

export interface Metrics {
  observed_runs: number;
  reviewed_runs: number; // terminal reviews only; "triaged" never counted
  triaged_runs: number;
  global_coverage: number | null;
  coverage_reason?: string;
  queued_jobs: number;
  daemon_running: boolean;
  window_start: string | null;
  window_end: string | null;
}

export interface Capabilities {
  semantic_review?: string;
  strong_sandbox?: string;
  promotion?: string;
  hook_trust?: string;
  recursive_gain?: string;
  [key: string]: unknown;
}

export interface ObservatoryState {
  skills: Skill[];
  runs: Run[];
  reviews: Review[];
  experiments: Experiment[];
  installations: Installation[];
  jobs: Job[];
  environments: Environment[];
  metrics: Metrics;
  settings: Settings;
  capabilities: Capabilities;
  capability_catalog?: Capability[];
  capability_versions?: CapabilityVersion[];
  capability_invocations?: Invocation[];
  captures?: Capture[];
  lifecycle_metrics?: Record<string, number>;
}

export interface SessionInfo {
  csrf: string;
}

export interface ApiError {
  status: number;
  message: string;
  offline?: boolean;
  reason_code?: string;
}

export interface Capability extends Skill {
 kind: "skill" | "script";
 purpose?: string; background?: string; scope: string; version_id: string;
 born_at?: string | null; first_seen_at: string;
 origin?: { session_id: string; turn_id: string; project: string; scenario: string; evidence_sha256: string } | null;
 usage_counts?: Record<string, number>; locations?: string[];
}
export interface CapabilityVersion {
 id: string; capability_id: string; package_sha256: string; created_at: string;
 manifest: {files: Record<string, string>}; snapshot_sha256: string;
}
export interface Invocation {
 id: string; capability_id: string; version_id: string; session_id: string; turn_id: string;
 cwd: string; scenario?: string; origin: string; stages: string[]; sources: string[];
 attempts: string[]; evidence_ids: string[]; created_at: string; status?: string;
}
export interface Capture {
 id: string; name: string; purpose: string; background: string; owner: string;
 origin: Capability["origin"]; kind?: string; decision: string; status: string;
 created_at: string; updated_at?: string; capability_id?: string;
 validation?: {status: string; reason_code?: string; evidence_sha256?: string; positive_passed?: number; negative_passed?: number};
 reason_code?: string; missing?: string[];
}
