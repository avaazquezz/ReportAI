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

export type FieldType = 'str' | 'int' | 'float' | 'bool' | 'date' | 'list[str]' | 'list[int]'

export interface FieldSchemaEntry {
  type: FieldType
  description: string
  required: boolean
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
