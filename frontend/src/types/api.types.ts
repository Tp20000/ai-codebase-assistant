/**
 * API Type Definitions — Shared across all services and components
 * Matches the Pydantic schemas defined in the FastAPI backend exactly.
 * Using strict TypeScript — zero implicit any types.
 */

// ─────────────────────────────────────────────
// Auth Types
// ─────────────────────────────────────────────

/** User registration request payload */
export interface RegisterRequest {
  email: string
  username: string
  password: string
  full_name?: string
}

/** Login request payload */
export interface LoginRequest {
  email: string
  password: string
}

/** Token refresh request */
export interface RefreshRequest {
  refresh_token: string
}

/** JWT token pair response from login/refresh */
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in: number
}

/** Authenticated user profile */
export interface UserProfile {
  id: string
  email: string
  username: string
  full_name: string | null
  is_active: boolean
  is_verified: boolean
  created_at: string
}

// ─────────────────────────────────────────────
// Project Types
// ─────────────────────────────────────────────

/** Project status enum */
export type ProjectStatus = 'pending' | 'indexing' | 'ready' | 'error'

/** Project language type */
export type ProjectLanguage =
  | 'python' | 'javascript' | 'typescript' | 'java'
  | 'cpp' | 'go' | 'rust' | 'ruby' | 'php' | 'csharp' | 'mixed'

/** Project model */
export interface Project {
  id: string
  name: string
  description: string | null
  language: ProjectLanguage
  status: ProjectStatus
  file_count: number
  total_size_bytes: number
  owner_id: string
  created_at: string
  updated_at: string
  indexed_at: string | null
}

/** Create project request */
export interface CreateProjectRequest {
  name: string
  description?: string
  language?: ProjectLanguage
}

// ─────────────────────────────────────────────
// File Types
// ─────────────────────────────────────────────

/** Code file in a project */
export interface CodeFile {
  id: string
  project_id: string
  path: string
  name: string
  extension: string
  size_bytes: number
  language: string
  is_indexed: boolean
  created_at: string
}

// ─────────────────────────────────────────────
// Chat Types
// ─────────────────────────────────────────────

/** Message role in conversation */
export type MessageRole = 'user' | 'assistant' | 'system'

/** Single chat message */
export interface ChatMessage {
  id: string
  session_id: string
  role: MessageRole
  content: string
  tokens_used: number | null
  model_used: string | null
  created_at: string
}

/** Chat session */
export interface ChatSession {
  id: string
  project_id: string
  user_id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

/** Send message request */
export interface SendMessageRequest {
  content: string
  session_id?: string
}

/** Streaming message chunk from WebSocket */
export interface StreamChunk {
  type: 'chunk' | 'done' | 'error' | 'sources'
  content?: string
  sources?: RetrievedSource[]
  error?: string
  message_id?: string
}

/** RAG retrieved source document */
export interface RetrievedSource {
  file_path: string
  chunk_content: string
  score: number
  line_start: number | null
  line_end: number | null
}

// ─────────────────────────────────────────────
// Agent Types
// ─────────────────────────────────────────────

/** Available agent tools */
export type AgentType =
  | 'bug_finder'
  | 'doc_generator'
  | 'test_writer'
  | 'code_reviewer'
  | 'security_scanner'
  | 'refactor_agent'
  | 'performance_agent'

/** Agent task status */
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

/** Agent task */
export interface AgentTask {
  id: string
  project_id: string
  agent_type: AgentType
  status: TaskStatus
  progress: number
  result: AgentResult | null
  error: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

/** Agent result with findings */
export interface AgentResult {
  summary: string
  findings: AgentFinding[]
  recommendations: string[]
  metrics: Record<string, number | string>
  files_analyzed: number
}

/** Single agent finding */
export interface AgentFinding {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  category: string
  title: string
  description: string
  file_path: string | null
  line_number: number | null
  suggestion: string | null
  code_snippet: string | null
}

// ─────────────────────────────────────────────
// Health & System Types
// ─────────────────────────────────────────────

/** Service health status */
export type ServiceStatus = 'healthy' | 'degraded' | 'unhealthy' | 'not_running'

/** Health check response */
export interface HealthResponse {
  status: ServiceStatus
  version: string
  environment: string
  uptime_seconds: number
  services: Record<string, {
    status: ServiceStatus
    latency_ms?: number
    version?: string
    error?: string
  }>
}

// ─────────────────────────────────────────────
// API Error Types
// ─────────────────────────────────────────────

/** Standard API error response */
export interface ApiError {
  detail: string | { msg: string; type: string }[]
  request_id?: string
}

/** Paginated list response */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}
