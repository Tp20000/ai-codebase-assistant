/**
 * Application Constants
 * Single source of truth for all magic strings and configuration values.
 */

/** API base URL — uses Vite proxy in dev, env var in production */
export const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** WebSocket base URL */
export const WS_BASE_URL =
  import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000'

/** Application name */
export const APP_NAME = 'AI Codebase Assistant'

/** Application version */
export const APP_VERSION = '2.0.0'

/** localStorage keys */
export const STORAGE_KEYS = {
  ACCESS_TOKEN:  'aca:access_token',
  REFRESH_TOKEN: 'aca:refresh_token',
  USER:          'aca:user',
  THEME:         'aca:theme',
  SIDEBAR_OPEN:  'aca:sidebar_open',
} as const

/** Query cache keys for TanStack Query */
export const QUERY_KEYS = {
  HEALTH:    ['health']          as const,
  ME:        ['auth', 'me']      as const,
  PROJECTS:  ['projects']        as const,
  PROJECT:   (id: string) => ['projects', id] as const,
  FILES:     (projectId: string) => ['files', projectId] as const,
  SESSIONS:  (projectId: string) => ['sessions', projectId] as const,
  MESSAGES:  (sessionId: string) => ['messages', sessionId] as const,
  TASKS:     (projectId: string) => ['tasks', projectId] as const,
  ANALYTICS: (projectId: string) => ['analytics', projectId] as const,
} as const

/** TanStack Query stale times */
export const STALE_TIMES = {
  NEVER:   0,
  SHORT:   30_000,   // 30 seconds
  MEDIUM:  300_000,  // 5 minutes
  LONG:    3_600_000, // 1 hour
} as const

/** WebSocket event types */
export const WS_EVENTS = {
  CHAT_CHUNK:      'chat:chunk',
  CHAT_DONE:       'chat:done',
  CHAT_ERROR:      'chat:error',
  TASK_PROGRESS:   'task:progress',
  TASK_COMPLETE:   'task:complete',
  TASK_ERROR:      'task:error',
  INDEXING_START:  'indexing:start',
  INDEXING_DONE:   'indexing:done',
} as const

/** File upload limits */
export const UPLOAD_LIMITS = {
  MAX_FILE_SIZE_MB: 100,
  MAX_FILE_SIZE_BYTES: 100 * 1024 * 1024,
  ALLOWED_EXTENSIONS: [
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java',
    '.cpp', '.c', '.h', '.go', '.rs', '.rb',
    '.php', '.cs', '.zip',
  ],
} as const

/** Agent display metadata */
export const AGENT_CONFIG = {
  bug_finder: {
    label: 'Bug Finder',
    description: 'Detect bugs and logic errors using AI analysis',
    icon: 'Bug',
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
  },
  doc_generator: {
    label: 'Doc Generator',
    description: 'Generate JSDoc and Python docstrings automatically',
    icon: 'FileText',
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
  },
  test_writer: {
    label: 'Test Writer',
    description: 'Write pytest and Jest unit tests for your code',
    icon: 'TestTube',
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
  },
  code_reviewer: {
    label: 'Code Reviewer',
    description: 'Review code style, patterns, and complexity',
    icon: 'Eye',
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/10',
  },
  security_scanner: {
    label: 'Security Scanner',
    description: 'Detect OWASP vulnerabilities and secret leaks',
    icon: 'Shield',
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-500/10',
  },
  refactor_agent: {
    label: 'Refactor Agent',
    description: 'Suggest SOLID, DRY, and KISS improvements',
    icon: 'Wand2',
    color: 'text-pink-400',
    bgColor: 'bg-pink-500/10',
  },
  performance_agent: {
    label: 'Performance Analyzer',
    description: 'Find bottlenecks and complexity issues',
    icon: 'Zap',
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
  },
} as const

/** Supported programming languages */
export const SUPPORTED_LANGUAGES = [
  { value: 'python',     label: 'Python',     icon: '🐍' },
  { value: 'javascript', label: 'JavaScript',  icon: '🟨' },
  { value: 'typescript', label: 'TypeScript',  icon: '🔷' },
  { value: 'java',       label: 'Java',        icon: '☕' },
  { value: 'cpp',        label: 'C++',         icon: '⚡' },
  { value: 'go',         label: 'Go',          icon: '🐹' },
  { value: 'rust',       label: 'Rust',        icon: '🦀' },
  { value: 'mixed',      label: 'Mixed',       icon: '🔀' },
] as const

/** App metadata */
export const APP = {
  NAME:    "AI Codebase Assistant",
  VERSION: "2.0.0",
  TAGLINE: "Understand your codebase with AI",
} as const;
/** Agent IDs matching backend AGENT_REGISTRY */
export const AGENT_IDS = {
  BUG_FINDER:           "bug_finder",
  DOC_GENERATOR:        "doc_generator",
  TEST_WRITER:          "test_writer",
  CODE_REVIEWER:        "code_reviewer",
  SECURITY_SCANNER:     "security_scanner",
  REFACTOR_SUGGESTER:   "refactor_suggester",
  PERFORMANCE_ANALYZER: "performance_analyzer",
} as const;