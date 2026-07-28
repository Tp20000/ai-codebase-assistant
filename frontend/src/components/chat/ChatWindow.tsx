/**
 * Chat Window Component - Step 45
 * AI Codebase Assistant v2.0
 *
 * Full-featured chat interface with:
 *   - Message history (user + AI bubbles)
 *   - Streaming response display
 *   - Typing indicator while AI generates
 *   - Auto-scroll to latest message
 *   - File context awareness (shows which file is selected)
 *   - Keyboard shortcut: Enter to send, Shift+Enter for newline
 *   - Error state visible in UI (never console-only)
 *   - Empty state with suggested questions
 *   - Loading state for initial session fetch
 */

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import toast from "react-hot-toast";

import { MessageBubble } from "@/components/chat/MessageBubble";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import {
  streamMessage,
  generateMessageId,
  type ChatMessage,
} from "@/services/chatService";
import type { ProjectFileInfo } from "@/services/fileService";

// ── Suggested questions ───────────────────────────────────────────

const SUGGESTED_QUESTIONS = [
  "What does this project do?",
  "Explain the main architecture",
  "Find potential security issues",
  "What are the main entry points?",
  "How is authentication handled?",
  "What dependencies does this project use?",
];

// ── ChatWindow Component ──────────────────────────────────────────

interface ChatWindowProps {
  /** Target project ID */
  projectId: string;
  /** Currently selected file for context */
  selectedFile: ProjectFileInfo | null;
  /** Content of the selected file (for direct LLM context injection) */
  selectedFileContent?: string | null;
  /** Optional pre-existing session ID to continue */
  sessionId?: string;
  /** Called when a new session is created */
  onSessionCreated?: (sessionId: string) => void;
}

/**
 * Full chat interface with streaming AI responses.
 *
 * States:
 *   Empty    — welcome screen with suggested questions
 *   Loading  — typing indicator while AI responds
 *   Messages — scrollable message history
 *   Error    — visible error banner with retry option
 */
export function ChatWindow({
  projectId,
  selectedFile,
  selectedFileContent,
  sessionId: initialSessionId,
  onSessionCreated,
}: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>(
    initialSessionId
  );
  const [error, setError] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  // Auto-resize textarea
  const adjustTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  }, []);

  useEffect(() => {
    adjustTextarea();
  }, [input, adjustTextarea]);

  // Send message handler
  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || isGenerating) return;

    setInput("");
    setError(null);

    // Add user message immediately
    const userMsg: ChatMessage = {
      id: generateMessageId(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Prepare AI response placeholder
    const aiMsgId = generateMessageId();
    setStreamingMessageId(aiMsgId);
    setIsGenerating(true);

    const aiMsg: ChatMessage = {
      id: aiMsgId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      is_streaming: true,
    };
    setMessages((prev) => [...prev, aiMsg]);

    try {
      // Build enriched query with actual file content for LLM context
      let enrichedQuery = content;
      if (selectedFile?.file_path && selectedFileContent) {
        enrichedQuery = `User Question: ${content}

File Being Analyzed: ${selectedFile.file_path}

File Content:
\`\`\`
${selectedFileContent.slice(0, 3000)}
\`\`\`

Please answer the user's question based on the file content above.`;
      } else if (selectedFile?.file_path) {
        enrichedQuery = `[Regarding file: ${selectedFile.file_path}] ${content}`;
      }

      await streamMessage(
        {
          project_id: projectId,
          session_id: currentSessionId,
          content: enrichedQuery,
          file_context: selectedFile?.file_path,
          code_context: selectedFileContent ?? undefined,
          model: "tinyllama",
        },
        // onChunk: append text to streaming message
        (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiMsgId
                ? { ...m, content: m.content + chunk }
                : m
            )
          );
        },
        // onDone: finalize the message
        (response) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiMsgId
                ? {
                    ...m,
                    is_streaming: false,
                    sources: response.sources ?? [],
                    content: response.content || m.content,
                  }
                : m
            )
          );

          if (response.session_id && !currentSessionId) {
            setCurrentSessionId(response.session_id);
            onSessionCreated?.(response.session_id);
          }

          setIsGenerating(false);
          setStreamingMessageId(null);
        },
        // onError: show visible error
        (errMsg) => {
          setError(errMsg);
          // Replace streaming message with error placeholder
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiMsgId
                ? {
                    ...m,
                    content: "Sorry, I encountered an error. Please try again.",
                    is_streaming: false,
                  }
                : m
            )
          );
          setIsGenerating(false);
          setStreamingMessageId(null);
        }
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      setIsGenerating(false);
      setStreamingMessageId(null);
    }
  }, [
    input,
    isGenerating,
    projectId,
    currentSessionId,
    selectedFile,
    onSessionCreated,
  ]);

  // Keyboard: Enter sends, Shift+Enter newline
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  // Suggested question click
  const handleSuggestion = useCallback(
    (question: string) => {
      setInput(question);
      textareaRef.current?.focus();
    },
    []
  );

  const hasMessages = messages.length > 0;
  const fileName = selectedFile?.file_path.split("/").pop();

  return (
    <div className="h-full flex flex-col bg-[var(--bg-secondary)]">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="flex-shrink-0 px-4 py-2.5 border-b border-[var(--border)]">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            AI Assistant
          </p>
          {hasMessages && (
            <button
              onClick={() => {
                setMessages([]);
                setCurrentSessionId(undefined);
                setError(null);
              }}
              className="text-[10px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              title="Start new conversation"
            >
              New chat
            </button>
          )}
        </div>
        {selectedFile && (
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5 truncate">
            Context: {fileName}
          </p>
        )}
      </div>

      {/* ── Messages ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 flex flex-col">
        {/* Error banner */}
        <ErrorBanner
          message={error}
          onDismiss={() => setError(null)}
        />

        {/* Empty state */}
        {!hasMessages && !error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center flex-1 text-center px-4 py-8"
          >
            <div className="text-3xl mb-3">🤖</div>
            <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
              Ask about your codebase
            </p>
            <p className="text-xs text-[var(--text-muted)] mb-5 max-w-xs">
              {selectedFile
                ? `Analyzing: ${fileName}`
                : "Select a file for context, or ask about the whole project"}
            </p>

            {/* Suggested questions */}
            <div className="grid grid-cols-1 gap-1.5 w-full max-w-sm">
              {SUGGESTED_QUESTIONS.slice(0, 6).map((q) => (
                <button
                  key={q}
                  onClick={() => handleSuggestion(q)}
                  className="
                    text-left text-xs px-3 py-2 rounded-lg
                    bg-[var(--bg-tertiary)] border border-[var(--border)]
                    text-[var(--text-secondary)]
                    hover:border-[var(--border-focus)] hover:text-[var(--text-primary)]
                    transition-colors
                  "
                >
                  {q}
                </button>
              ))}
            </div>
          </motion.div>
        )}

        {/* Message list */}
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
            >
              <MessageBubble
                message={msg}
                isStreaming={msg.id === streamingMessageId}
              />
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator (shown while waiting for first chunk) */}
        {isGenerating &&
          messages[messages.length - 1]?.content === "" && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2"
            >
              <div className="w-7 h-7 rounded-full bg-[var(--bg-tertiary)] border border-[var(--border)] flex items-center justify-center text-xs text-[var(--text-muted)]">
                AI
              </div>
              <div className="bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-2xl rounded-tl-sm">
                <TypingIndicator />
              </div>
            </motion.div>
          )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Input ──────────────────────────────────────────────── */}
      <div className="flex-shrink-0 p-3 border-t border-[var(--border)]">
        <div className={clsx(
          "flex items-end gap-2 rounded-xl border transition-colors",
          "bg-[var(--bg-tertiary)]",
          isGenerating
            ? "border-[var(--border)] opacity-70"
            : "border-[var(--border)] focus-within:border-[var(--border-focus)]"
        )}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isGenerating
                ? "AI is thinking..."
                : selectedFile
                ? `Ask about ${fileName}...`
                : "Ask about your codebase..."
            }
            disabled={isGenerating}
            rows={1}
            className="
              flex-1 px-3 py-2.5 text-xs bg-transparent resize-none
              text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
              focus:outline-none disabled:cursor-not-allowed
              min-h-[38px] max-h-[120px]
            "
            style={{ scrollbarWidth: "none" }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isGenerating}
            className={clsx(
              "flex-shrink-0 m-1.5 w-8 h-8 rounded-lg flex items-center justify-center",
              "transition-all duration-150",
              input.trim() && !isGenerating
                ? "bg-blue-500 text-white hover:bg-blue-600 active:scale-95"
                : "bg-[var(--bg-hover)] text-[var(--text-muted)] cursor-not-allowed"
            )}
            aria-label="Send message"
          >
            {isGenerating ? (
              <div className="w-3 h-3 rounded-full border border-[var(--text-muted)] border-t-transparent animate-spin" />
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            )}
          </button>
        </div>

        <p className="text-[10px] text-[var(--text-muted)] text-center mt-1.5">
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}