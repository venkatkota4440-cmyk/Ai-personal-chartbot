/**
 * API contracts shared by the web app. Keep in sync with apps/api/app/schemas.
 * Dates are ISO-8601 strings in UTC.
 */

export type ErrorCategory =
  | "validation_error"
  | "authentication_required"
  | "invalid_credentials"
  | "forbidden"
  | "csrf_failed"
  | "not_found"
  | "conflict"
  | "rate_limited"
  | "payload_too_large"
  | "internal_error"
  | "service_unavailable"
  | "ai_unavailable"
  | "ai_invalid_output"
  | "ai_refused"
  // Produced by the web client when the API cannot be reached at all.
  | "network_error";

export interface FieldError {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  error: {
    category: ErrorCategory;
    message: string;
    request_id: string | null;
    fields?: FieldError[];
  };
}

export interface User {
  id: string;
  email: string;
  timezone: string;
  created_at: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  timezone: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserSettings {
  timezone: string;
  default_model: string;
  available_models: string[];
  notify_run_succeeded: boolean;
  notify_run_failed: boolean;
  notify_approval_needed: boolean;
  /** null = keep conversation messages until deleted. */
  message_retention_days: number | null;
}

export type SettingsUpdate = Partial<Omit<UserSettings, "available_models">>;

export interface HealthResponse {
  status: "ok" | "degraded";
  components: Record<string, "ok" | "unavailable">;
}

/** Every automation run ends in exactly one of these states (never a silent success). */
export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "partially_succeeded"
  | "failed"
  | "cancelled";

export type RiskLevel = "low" | "medium" | "high" | "prohibited";

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired" | "consumed";

// ---- M2: chat and memory -------------------------------------------------

export type MemoryStatus = "proposed" | "approved" | "rejected";

export interface Memory {
  id: string;
  content: string;
  /** "user" = typed by the user; "chat" = suggested by the assistant in a conversation. */
  source: string;
  status: MemoryStatus;
  conversation_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryUpdate {
  content?: string;
  status?: "approved" | "rejected";
}

export interface UsedMemory {
  id: string;
  /** null when the memory was deleted after the reply. */
  content: string | null;
  status: "current" | "edited" | "deleted";
}

export type Confidence = "high" | "medium" | "low";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  confidence: Confidence | null;
  human_review_note: string | null;
  used_memories: UsedMemory[];
  /** How memories were matched; null when memory was off for the reply. */
  memory_ranking: "keyword" | null;
  model: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  memory_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

export interface ChatSendRequest {
  message: string;
  conversation_id?: string;
  memory_enabled?: boolean;
}

export interface ChatResponse {
  conversation: Conversation;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  proposed_memories: Memory[];
}

// ---- M3: projects and tasks ---------------------------------------------

export type ProjectStatus = "active" | "paused" | "completed" | "archived";
export type TaskStatus = "todo" | "in_progress" | "blocked" | "done";
export type TaskPriority = "low" | "medium" | "high" | "urgent";

export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
  task_total: number;
  task_done: number;
  task_open: number;
}

export interface Task {
  id: string;
  project_id: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---- M4/M5: automations, runs, approvals, notifications -------------------

export type TriggerType = "manual" | "schedule" | "event";
export type StepStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "failed"
  | "skipped"
  | "blocked"
  | "cancelled";

export interface WorkflowStep {
  type: string;
  params: Record<string, unknown>;
}

export interface Automation {
  id: string;
  name: string;
  trigger_type: TriggerType;
  cron: string | null;
  enabled: boolean;
  version: number;
  definition: { steps?: WorkflowStep[] };
  permission_policy: { auto_allowed?: string[]; require_approval?: string[] };
  created_at: string;
  updated_at: string;
}

/** Risk is classified by the backend; the UI only displays it. */
export interface StepRisk {
  type: string;
  risk: RiskLevel;
  automatic: "yes" | "no";
  reason: string;
}

export interface AutomationDetail extends Automation {
  step_risks: StepRisk[];
  last_run: Run | null;
  next_run_hint: string | null;
}

export interface Run {
  id: string;
  automation_id: string;
  automation_version: number;
  trigger: TriggerType;
  status: RunStatus;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  output_summary: string | null;
  error_category: string | null;
  error_message_sanitized: string | null;
}

export interface RunStep {
  id: string;
  step_index: number;
  type: string;
  status: StepStatus;
  risk_level: RiskLevel | null;
  attempts: number;
  input_summary: string | null;
  output_summary: string | null;
  error_message_sanitized: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunDetail extends Run {
  automation_name: string;
  steps: RunStep[];
  pending_approval_id: string | null;
}

export interface Approval {
  id: string;
  run_id: string;
  action_type: string;
  action_summary: string;
  target: string;
  payload_preview: string;
  payload_hash: string;
  risk_explanation: string;
  likely_consequence: string;
  status: ApprovalStatus;
  created_at: string;
  expires_at: string;
  decided_at: string | null;
  decision_reason: string | null;
}

export interface Notification {
  id: string;
  type: string;
  message: string;
  link: string | null;
  read_at: string | null;
  created_at: string;
}
