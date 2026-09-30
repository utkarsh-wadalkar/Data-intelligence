export type Field = {
  name: string;
  label: string;
  type: "text" | "number" | "date" | "url" | "boolean";
  description: string;
};
export type Workflow = {
  id: string;
  creator_id: string;
  prompt: string;
  title: string;
  queries: string[];
  fields: Field[];
  identity_fields: string[];
  status: "draft" | "active";
  cadence: "none" | "daily" | "weekly";
  local_hour: number;
  week_day: number;
  timezone: string;
  next_run_at: string | null;
  pause_reason: string | null;
  created_at: string;
};
export type Run = {
  id: string;
  workflow_id: string;
  trigger: string;
  status: string;
  stage: string;
  pause_reason: string | null;
  error: string | null;
  searched: number;
  scraped: number;
  observations: number;
  retry_attempt: number;
  next_retry_at: string | null;
  recovery_count: number;
  created_at: string;
  finished_at: string | null;
};
export type RecordRow = {
  id: string;
  data: Record<string, string | number | boolean | null>;
  source_id: string;
  source_url: string;
  fetched_at: string;
  evidence: string;
  first_seen_at: string;
  last_seen_at: string;
  observation_count: number;
};
export type Source = {
  id: string;
  url: string;
  title: string;
  excerpt: string;
  fetched_at: string;
  run_id: string;
};
