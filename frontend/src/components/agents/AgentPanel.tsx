/**
 * Agent Panel - Step 47
 * AI Codebase Assistant v2.0
 *
 * Full agent runner panel:
 *   - Grid of agent selector cards
 *   - Run selected agent against open file
 *   - Real-time progress via polling
 *   - Task history with status
 *   - Report viewer overlay
 *
 * States: idle | running | report_view
 */

import { useState, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { clsx } from "clsx";
import toast from "react-hot-toast";

import { AgentTaskCard } from "@/components/agents/AgentTask";
import { AgentReport } from "@/components/agents/AgentReport";
import {
  ALL_AGENTS,
  runAgentDirect,
  pollTaskUntilDone,
  queueAgentTask,
  getTaskStatus,
  type AgentId,
  type AgentMeta,
  type AgentTaskResult,
} from "@/services/agentService";
import type { ProjectFileInfo } from "@/services/fileService";
import { useAuthStore } from "@/stores/authStore";

// ── Agent Selector Card ───────────────────────────────────────────

interface AgentCardProps {
  agent: AgentMeta;
  isSelected: boolean;
  isRunning: boolean;
  onClick: () => void;
}

function AgentCard({ agent, isSelected, isRunning, onClick }: AgentCardProps) {
  return (
    <button
      onClick={onClick}
      disabled={isRunning}
      className={clsx(
        "flex flex-col items-start gap-1.5 p-3 rounded-lg border text-left transition-all",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        isSelected
          ? "border-blue-500/60 bg-blue-500/10"
          : "border-[var(--border)] bg-[var(--bg-tertiary)] hover:border-[var(--border-focus)] hover:bg-[var(--bg-hover)]"
      )}
    >
      <div className="flex items-center gap-2 w-full">
        <span className="text-lg flex-shrink-0">{agent.icon}</span>
        <span
          className="text-xs font-semibold truncate"
          style={{ color: isSelected ? agent.color : "var(--text-primary)" }}
        >
          {agent.display}
        </span>
      </div>
      <p className="text-[10px] text-[var(--text-muted)] leading-tight line-clamp-2">
        {agent.description}
      </p>
    </button>
  );
}

// ── Agent Panel ───────────────────────────────────────────────────

interface AgentPanelProps {
  projectId: string;
  selectedFile: ProjectFileInfo | null;
  selectedFileContent?: string | null;
}

/**
 * Full agent panel with selection, execution, and report viewing.
 */
export function AgentPanel({
  projectId,
  selectedFile,
  selectedFileContent,
}: AgentPanelProps) {
  const { user } = useAuthStore();
  const [selectedAgentId, setSelectedAgentId] = useState<AgentId | null>(null);
  const [tasks, setTasks] = useState<AgentTaskResult[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [viewingReport, setViewingReport] = useState<AgentTaskResult | null>(null);

  const userId = user?.id ?? "anonymous";

  const handleRun = useCallback(async () => {
    if (!selectedAgentId) {
      toast("Please select an agent first", { icon: "💡" });
      return;
    }
    if (!selectedFile || !selectedFileContent) {
      toast("Please open a file first", { icon: "📄" });
      return;
    }

    setIsRunning(true);

    // Create placeholder task
    const placeholder: AgentTaskResult = {
      task_id: `local-${Date.now()}`,
      agent_id: selectedAgentId,
      status: "RUNNING",
      progress: 0,
      current_step: "Starting...",
    };
    setTasks((prev) => [placeholder, ...prev]);

    try {
      // Run agent directly (synchronous - bypasses Celery for reliability)
      try {
        const result = await runAgentDirect(
          selectedAgentId,
          projectId,
          userId,
          selectedFileContent,
          selectedFile.language || "unknown",
          selectedFile.file_path
        );

        // Update task with result
        const final: AgentTaskResult = {
          ...placeholder,
          task_id: result.task_id || placeholder.task_id,
          status: result.status || "COMPLETED",
          progress: 1.0,
          report: result.report ?? null,
          result: result.result ?? null,
          error: result.error ?? null,
          elapsed_ms: result.elapsed_ms,
        };

        setTasks((prev) =>
          prev.map((t) =>
            t.task_id === placeholder.task_id ? final : t
          )
        );

        var taskFinal = final;
      } catch (runErr) {
        const final: AgentTaskResult = {
          ...placeholder,
          status: "FAILED",
          progress: 0,
          error: runErr instanceof Error ? runErr.message : "Agent run failed",
        };
        setTasks((prev) =>
          prev.map((t) =>
            t.task_id === placeholder.task_id ? final : t
          )
        );
        var taskFinal = final;
      }

      const finalResult = taskFinal!;

      if (finalResult.status === "COMPLETED") {
        toast.success(`${selectedAgentId.replace("_", " ")} completed!`);
        setViewingReport(finalResult);
      } else {
        toast.error(`Agent failed: ${finalResult.error ?? "Unknown error"}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Agent run failed";
      toast.error(msg);

      setTasks((prev) =>
        prev.map((t) =>
          t.task_id === placeholder.task_id
            ? {
                ...t,
                status: "FAILED" as const,
                error: msg,
                progress: 0,
              }
            : t
        )
      );
    } finally {
      setIsRunning(false);
    }
  }, [selectedAgentId, selectedFile, selectedFileContent, projectId, userId]);

  // Showing report overlay
  if (viewingReport) {
    return (
      <AgentReport
        task={viewingReport}
        onClose={() => setViewingReport(null)}
      />
    );
  }

  return (
    <div className="h-full min-h-0 flex flex-col bg-[var(--bg-secondary)]">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-[var(--border)]">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          AI Agents
        </p>
        <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
          {selectedFile
            ? `Target: ${selectedFile.file_path.split("/").pop()}`
            : "Open a file then select an agent"}
        </p>
      </div>

      {/* Agent grid */}
      <div className="flex-shrink-0 p-3 border-b border-[var(--border)]">
        <div className="grid grid-cols-2 gap-1.5">
          {ALL_AGENTS.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              isSelected={selectedAgentId === agent.id}
              isRunning={isRunning}
              onClick={() =>
                setSelectedAgentId((prev) =>
                  prev === agent.id ? null : agent.id
                )
              }
            />
          ))}
        </div>

        {/* Run button */}
        <button
          onClick={handleRun}
          disabled={isRunning || !selectedAgentId || !selectedFile}
          className={clsx(
            "mt-3 w-full py-2 text-sm font-medium rounded-lg transition-all",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            selectedAgentId && selectedFile && !isRunning
              ? "bg-gradient-to-r from-blue-500 to-purple-600 text-white hover:from-blue-600 hover:to-purple-700"
              : "bg-[var(--bg-tertiary)] text-[var(--text-muted)] border border-[var(--border)]"
          )}
        >
          {isRunning ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
              Running...
            </span>
          ) : selectedAgentId ? (
            `Run ${ALL_AGENTS.find((a) => a.id === selectedAgentId)?.display ?? "Agent"}`
          ) : (
            "Select an agent above"
          )}
        </button>
      </div>

      {/* Task history */}
      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="text-3xl mb-3">🤖</div>
            <p className="text-xs text-[var(--text-muted)]">
              No agent runs yet.
            </p>
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              Select an agent and click Run.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wide mb-2">
              Recent runs
            </p>
            <AnimatePresence>
              {tasks.map((task) => (
                <AgentTaskCard
                  key={task.task_id}
                  task={task}
                  onViewReport={setViewingReport}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}