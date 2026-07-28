/**
 * Agent Service - Step 47
 * AI Codebase Assistant v2.0
 *
 * Handles agent task queuing, status polling, and result retrieval.
 *
 * Flow:
 *   1. POST /tasks/agent  -> { task_id, status: "QUEUED" }
 *   2. GET  /tasks/{id}   -> { status, result, report, progress }
 *   3. Poll until status == COMPLETED or FAILED
 */

import { apiClient, getErrorMessage } from "@/services/api";


// ── Types ──────────────────────────────────────────────────────────

export type AgentId =
  | "bug_finder"
  | "doc_generator"
  | "test_writer"
  | "code_reviewer"
  | "security_scanner"
  | "refactor_suggester"
  | "performance_analyzer";

export type TaskStatus =
  | "QUEUED"
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface AgentTaskResult {
  task_id: string;
  agent_id: AgentId;
  status: TaskStatus;
  progress: number;          // 0.0 – 1.0
  current_step?: string;
  report?: string | null;    // Markdown report
  result?: Record<string, unknown> | null;
  error?: string | null;
  elapsed_ms?: number;
  created_at?: string;
}

export interface RunAgentRequest {
  agent_id: AgentId;
  project_id: string;
  user_id: string;
  code_content: string;
  language: string;
  file_path: string;
  model?: string;
}

export interface QueuedTaskResponse {
  task_id: string;
  status: "QUEUED";
  message: string;
  poll_url: string;
}

// ── Agent metadata helper ─────────────────────────────────────────

export interface AgentMeta {
  id: AgentId;
  display: string;
  description: string;
  icon: string;
  color: string;
}

export const ALL_AGENTS: AgentMeta[] = [
  {
    id: "bug_finder",
    display: "Bug Finder",
    description: "Detects logic errors and runtime bugs",
    icon: "🐛",
    color: "#EF4444",
  },
  {
    id: "doc_generator",
    display: "Doc Generator",
    description: "Generates Google/JSDoc documentation",
    icon: "📚",
    color: "#3B82F6",
  },
  {
    id: "test_writer",
    display: "Test Writer",
    description: "Writes pytest/Jest unit tests",
    icon: "🧪",
    color: "#10B981",
  },
  {
    id: "code_reviewer",
    display: "Code Reviewer",
    description: "Reviews style, patterns, complexity",
    icon: "🔍",
    color: "#8B5CF6",
  },
  {
    id: "security_scanner",
    display: "Security Scanner",
    description: "OWASP vulnerability detection",
    icon: "🛡️",
    color: "#F59E0B",
  },
  {
    id: "refactor_suggester",
    display: "Refactor Agent",
    description: "SOLID/DRY/KISS improvements",
    icon: "⚡",
    color: "#06B6D4",
  },
  {
    id: "performance_analyzer",
    display: "Performance",
    description: "Big-O and bottleneck detection",
    icon: "📊",
    color: "#84CC16",
  },
];

// ── API functions ──────────────────────────────────────────────────

/**
 * Queue an agent task for background execution.
 * Returns immediately with task_id — poll for results.
 */
export async function queueAgentTask(
  request: RunAgentRequest
): Promise<QueuedTaskResponse> {
  const response = await apiClient.post<QueuedTaskResponse>(
    "/tasks/agent",
    request
  );
  return response.data;
}

/**
 * Get current status and result of a task.
 */
export async function getTaskStatus(
  taskId: string
): Promise<AgentTaskResult> {
  const response = await apiClient.get<AgentTaskResult>(
    `/tasks/${taskId}`
  );
  return response.data;
}

/**
 * Get live progress from Redis (faster than full status).
 */
export async function getTaskProgress(
  taskId: string
): Promise<{
  status: TaskStatus;
  progress: number;
  current_step: string;
}> {
  const response = await apiClient.get<{
    status: TaskStatus;
    progress: number;
    current_step: string;
  }>(`/tasks/${taskId}/progress`);
  return response.data;
}

/**
 * Poll a task until it reaches a terminal state.
 *
 * @param taskId      Task UUID to poll
 * @param onProgress  Called on each poll with current status
 * @param intervalMs  Polling interval (default 2s)
 * @param timeoutMs   Max wait time (default 5 min)
 */
export async function pollTaskUntilDone(
  taskId: string,
  onProgress: (result: AgentTaskResult) => void,
  intervalMs = 2000,
  timeoutMs = 300_000
): Promise<AgentTaskResult> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const result = await getTaskStatus(taskId);
    onProgress(result);

    if (
      result.status === "COMPLETED" ||
      result.status === "FAILED" ||
      result.status === "CANCELLED"
    ) {
      return result;
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error(`Task ${taskId} timed out after ${timeoutMs / 1000}s`);
}

/**
 * Run an agent directly (synchronous, no Celery) for small files.
 * Falls back to task queue for larger workloads.
 */
export async function runAgentDirect(
  agentId: AgentId,
  projectId: string,
  userId: string,
  codeContent: string,
  language: string,
  filePath: string
): Promise<AgentTaskResult> {
  const meta = getAgentMeta(agentId);
  
  // Build an agent-specific prompt
  const agentPrompts: Record<AgentId, string> = {
    bug_finder: `Analyze this code for bugs, logic errors, and potential runtime issues. List each bug with line number, severity, and fix suggestion.`,
    doc_generator: `Generate comprehensive documentation for this code. Include docstrings for all functions and classes.`,
    test_writer: `Write complete unit tests for this code. Use pytest for Python, Jest for JavaScript/TypeScript.`,
    code_reviewer: `Review this code for quality, style, design patterns, and best practices. Rate overall quality out of 10.`,
    security_scanner: `Scan this code for security vulnerabilities. Check for OWASP Top 10 issues, hardcoded secrets, injection risks.`,
    refactor_suggester: `Suggest refactoring improvements for this code. Apply SOLID, DRY, KISS principles. Show before/after examples.`,
    performance_analyzer: `Analyze this code for performance bottlenecks. Identify O(n^2) loops, memory issues, and optimization opportunities.`,
  };

  const prompt = agentPrompts[agentId] || "Analyze this code.";

  try {
    // Create a chat session
    const session = await apiClient.post<{ session_id?: string; id?: string }>(
      "/chat/sessions",
      { project_id: projectId, title: `${meta.display} Analysis` }
    );
    const sessionId = session.data.session_id || session.data.id || "";

    // Use the working chat/ask endpoint with code_context
    const response = await apiClient.post<Record<string, unknown>>(
      `/chat/sessions/${sessionId}/ask`,
      {
        query: prompt,
        content: prompt,
        code_context: codeContent,
        file_context: filePath,
        model: "tinyllama",
      },
      { timeout: 120_000 }
    );

    const data = response.data;
    const answer = String(data.answer ?? data.content ?? data.response ?? data.message ?? "No result");

    return {
      task_id: sessionId,
      agent_id: agentId,
      status: "COMPLETED",
      progress: 1.0,
      report: `# ${meta.display} Report\n\n**File:** \`${filePath}\`\n**Language:** ${language}\n\n---\n\n${answer}`,
      result: { summary: answer.slice(0, 200) },
      error: null,
    };
  } catch (err) {
    throw new Error(getErrorMessage(err));
  }
}

export function getAgentMeta(agentId: AgentId): AgentMeta {
  return (
    ALL_AGENTS.find((a) => a.id === agentId) ?? {
      id: agentId,
      display: agentId,
      description: "",
      icon: "🤖",
      color: "#6B7280",
    }
  );
}