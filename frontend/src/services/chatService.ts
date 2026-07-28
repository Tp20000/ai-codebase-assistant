/**
 * Chat Service - Step 45 (stability fix)
 * AI Codebase Assistant v2.0
 *
 * Uses:
 *   POST /chat/sessions
 *   POST /chat/sessions/{session_id}/ask
 *
 * Adds timeout + simulated streaming fallback so UI never hangs forever.
 */

import { apiClient, getErrorMessage } from "@/services/api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  sources?: CodeSource[];
  is_streaming?: boolean;
}

export interface CodeSource {
  file_path: string;
  language: string;
  start_line: number;
  end_line: number;
  content: string;
  score?: number;
}

export interface SendMessageRequest {
  project_id: string;
  session_id?: string;
  content: string;
  file_context?: string;
  /** Actual file content to include as context for the AI */
  code_context?: string;
  model?: string;
}

export interface ChatResponse {
  session_id: string;
  content: string;
  sources: CodeSource[];
  answer?: string;
  response?: string;
  message?: string;
}

const SESSION_CACHE: Record<string, string> = {};

/**
 * Create or reuse a chat session for a project.
 */
async function getOrCreateSession(projectId: string): Promise<string> {
  if (SESSION_CACHE[projectId]) {
    return SESSION_CACHE[projectId];
  }

  const response = await apiClient.post<{ session_id?: string; id?: string }>(
    "/chat/sessions",
    {
      project_id: projectId,
      title: "New Chat",
    }
  );

  const sessionId = response.data.session_id ?? response.data.id;
  if (!sessionId) {
    throw new Error("Chat session ID not returned by backend");
  }

  SESSION_CACHE[projectId] = sessionId;
  return sessionId;
}

/**
 * Execute POST with timeout using AbortController-compatible pattern via Promise.race.
 */
async function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return await Promise.race([
    promise,
    new Promise<T>((_, reject) =>
      setTimeout(() => reject(new Error(`Request timed out after ${ms / 1000}s`)), ms)
    ),
  ]);
}

/**
 * Send a non-streaming message using the working backend endpoint.
 */
export async function sendMessage(
  request: SendMessageRequest
): Promise<ChatResponse> {
  const sessionId = request.session_id ?? await getOrCreateSession(request.project_id);

  const response = await withTimeout(
    apiClient.post<Record<string, unknown>>(
      `/chat/sessions/${sessionId}/ask`,
      {
        content: request.content,
        query: request.content,
        message: request.content,
        file_context: request.file_context,
        code_context: request.code_context,
        model: request.model ?? "tinyllama",
      }
    ),
    120000
  );

  const data = response.data;
  const content =
    String(
      data.content ??
      data.answer ??
      data.response ??
      data.message ??
      ""
    ) || "No response received.";

  return {
    session_id: String(data.session_id ?? sessionId),
    content,
    sources: (data.sources as CodeSource[]) ?? [],
    answer: typeof data.answer === "string" ? data.answer : undefined,
    response: typeof data.response === "string" ? data.response : undefined,
    message: typeof data.message === "string" ? data.message : undefined,
  };
}

/**
 * Simulated streaming: call REST endpoint once, then reveal word-by-word.
 * This guarantees the UI behaves like streaming even when backend SSE/WS
 * streaming is unavailable or not implemented yet.
 */
export async function streamMessage(
  request: SendMessageRequest,
  onChunk: (chunk: string) => void,
  onDone: (response: Partial<ChatResponse>) => void,
  onError: (error: string) => void
): Promise<void> {
  try {
    const result = await sendMessage(request);
    const words = result.content.split(" ");

    for (let i = 0; i < words.length; i++) {
      const chunk = words[i] + (i < words.length - 1 ? " " : "");
      onChunk(chunk);
      await new Promise((resolve) => setTimeout(resolve, 20));
    }

    onDone(result);
  } catch (err) {
    onError(getErrorMessage(err) || "Chat request failed");
  }
}

export function generateMessageId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export function formatMessageTime(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}