export interface User {
  id: string
  email: string
  full_name: string
  role: string
  tenant_id: string | null
  is_demo: boolean
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export interface Tenant {
  id: string
  name: string
  slug: string
  is_active: boolean
  created_at: string
}

export interface TenantCreateResponse extends Tenant {
  invite_email_sent: boolean
}

export interface TenantCreateRequest {
  name: string
  slug: string
  admin_email: string
  admin_full_name: string
}

// Must match the backend's FieldType literal (app/schemas/document_type.py).
export type ColumnType = 'str' | 'int' | 'float' | 'bool' | 'date' | 'time' | 'email' | 'phone'
export type FieldType = ColumnType | 'list[str]' | 'list[int]' | 'enum' | 'list[object]' | 'image'

export interface ColumnSpec {
  type: ColumnType
  description?: string
}

export interface FieldSchemaEntry {
  type: FieldType
  description: string
  // "Required to send": the bot asks for it when the message doesn't contain it.
  required: boolean
  label?: string | null
  options?: string[] | null // enum only
  columns?: Record<string, ColumnSpec> | null // list[object] (a table) only
  multiple?: boolean | null // image only
}

export interface DocumentType {
  id: string
  tenant_id: string
  name: string
  description: string | null
  field_schema: Record<string, FieldSchemaEntry>
  prompt_instructions: string | null
  notification_emails: string[]
  is_active: boolean
  created_at: string
}

export interface DocumentTypeWriteRequest {
  name: string
  description: string | null
  field_schema: Record<string, FieldSchemaEntry>
  prompt_instructions: string | null
  notification_emails: string[]
  is_active?: boolean
}

export interface DocumentTemplate {
  id: string
  tenant_id: string
  document_type_id: string
  original_filename: string
  version: number
  is_active: boolean
  uploaded_by: string | null
  created_at: string
}

export type ChannelType = 'telegram' | 'whatsapp' | 'email'

export interface ChannelConnection {
  id: string
  tenant_id: string
  channel_type: ChannelType
  display_name: string
  has_credentials: boolean
  allowed_senders: string[]
  is_active: boolean
  created_at: string
}

export interface ChannelConnectionCreateRequest {
  channel_type: ChannelType
  display_name: string
  credentials: Record<string, string>
  allowed_senders: string[]
}

export interface ChannelConnectionUpdateRequest {
  display_name: string
  credentials?: Record<string, string>
  allowed_senders: string[]
  is_active: boolean
}

export interface Report {
  id: string
  tenant_id: string
  document_type_id: string | null
  document_type_name: string | null
  status: string
  requester_channel: string
  requester_identifier: string
  error_detail: string | null
  download_url: string | null
  created_at: string
  completed_at: string | null
}

export type FieldValue = string | number | boolean | null | Array<string | number> | Array<Record<string, unknown>>

export interface ReportDelivery {
  id: string
  kind: 'channel' | 'email'
  destination: string
  status: 'pending' | 'sent' | 'failed'
  attempts: number
  last_error: string | null
  sent_at: string | null
  updated_at: string
}

export interface ReportStep {
  step: string
  status: string
  latency_ms: number | null
  cost_usd: number | null
  error_detail: string | null
  created_at: string
}

export interface ReportRevision {
  action: 'approve' | 'reject' | 'edit' | 'rerender' | 'resend'
  user_name: string | null
  changes: Record<string, { from: unknown; to: unknown }> | null
  note: string | null
  created_at: string
}

export interface ReportPhoto {
  id: string
  url: string
  caption: string | null
}

export interface ReportDetail extends Report {
  received_at: string | null
  updated_at: string
  source_text: string | null
  audio_url: string | null
  reject_reason: string | null
  extracted_fields: Record<string, FieldValue> | null
  evidence: Record<string, string> | null
  field_schema: Record<string, FieldSchemaEntry> | null
  photos: ReportPhoto[]
  deliveries: ReportDelivery[]
  steps: ReportStep[]
  revisions: ReportRevision[]
}

export interface ReportFilters {
  status?: string | null
  document_type_id?: string | null
  channel?: string | null
  created_from?: string | null
  created_to?: string | null
  q?: string | null
}

export interface DailyCostPoint {
  date: string
  cost_usd: number
}

export interface UsageSummary {
  total_cost_usd: number
  total_reports: number
  reports_by_status: Record<string, number>
  avg_latency_ms: number | null
  daily_cost: DailyCostPoint[]
}

declare module '#app' {
  interface PageMeta {
    // i18n key of the page's own browser-tab title (FE-11); the layout applies it.
    titleKey?: string
  }
}
