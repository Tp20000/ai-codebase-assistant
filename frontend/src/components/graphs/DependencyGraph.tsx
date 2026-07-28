/**
 * Dependency Graph Component - Step 48 (fixed edges)
 * AI Codebase Assistant v2.0
 *
 * FIX:
 *   Custom React Flow nodes must have Handle components,
 *   otherwise edges will not render.
 */

import { useCallback, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type NodeTypes,
  useNodesState,
  useEdgesState,
  Panel,
} from "reactflow";
import "reactflow/dist/style.css";
import { clsx } from "clsx";

// ── Custom Node ───────────────────────────────────────────────────

interface ModuleNodeData {
  label: string;
  file_path: string;
  language: string;
  node_type: string;
  imports_count: number;
  imported_by_count: number;
  is_entry_point: boolean;
  is_orphan: boolean;
  is_hub: boolean;
}

function ModuleNode({ data }: { data: ModuleNodeData }) {
  const typeColors: Record<string, string> = {
    entry_point: "#3B82F6",
    hub:         "#8B5CF6",
    orphan:      "#F59E0B",
    module:      "#6B7280",
  };

  const color = typeColors[data.node_type] || "#6B7280";

  const icons: Record<string, string> = {
    python: "🐍",
    javascript: "📜",
    typescript: "🔷",
    java: "☕",
    go: "🐹",
    rust: "🦀",
    cpp: "⚡",
    default: "📄",
  };

  const icon = icons[data.language] || icons.default;

  return (
    <div
      className="relative px-3 py-2 rounded-lg border-2 bg-[#161b22] text-white min-w-[120px] max-w-[200px] shadow-lg"
      style={{ borderColor: color }}
    >
      {/* Handles are REQUIRED for custom nodes so edges can render */}
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        style={{
          width: 8,
          height: 8,
          background: color,
          border: "1px solid #0d1117",
        }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        style={{
          width: 8,
          height: 8,
          background: color,
          border: "1px solid #0d1117",
        }}
      />

      {/* Optional top/bottom handles for nicer routing */}
      <Handle
        type="target"
        position={Position.Top}
        id="top"
        style={{
          width: 6,
          height: 6,
          background: color,
          border: "1px solid #0d1117",
          opacity: 0.7,
        }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        style={{
          width: 6,
          height: 6,
          background: color,
          border: "1px solid #0d1117",
          opacity: 0.7,
        }}
      />

      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-sm flex-shrink-0">{icon}</span>
        <span className="text-[11px] font-semibold truncate">{data.label}</span>
      </div>

      <div className="flex gap-2 text-[9px] text-gray-400">
        <span title="Imports">→ {data.imports_count}</span>
        <span title="Imported by">← {data.imported_by_count}</span>
      </div>

      {(data.is_entry_point || data.is_hub || data.is_orphan) && (
        <div
          className="mt-1 text-[8px] font-medium px-1.5 py-0.5 rounded-full inline-block"
          style={{ backgroundColor: color + "30", color }}
        >
          {data.is_entry_point ? "entry" : data.is_hub ? "hub" : "orphan"}
        </div>
      )}
    </div>
  );
}

const nodeTypes: NodeTypes = {
  moduleNode: ModuleNode,
};

// ── Props ─────────────────────────────────────────────────────────

interface DependencyGraphProps {
  nodes: Node<ModuleNodeData>[];
  edges: Edge[];
  metadata?: {
    total_files: number;
    total_edges: number;
    circular_count: number;
    orphan_count: number;
    circular_dependencies?: Array<{ cycle: string[] }>;
  };
  className?: string;
}

/**
 * Interactive dependency graph with React Flow.
 */
export function DependencyGraph({
  nodes: initialNodes,
  edges: initialEdges,
  metadata,
  className,
}: DependencyGraphProps) {
  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNode, setSelectedNode] = useState<ModuleNodeData | null>(null);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node<ModuleNodeData>) => {
      setSelectedNode(node.data);
    },
    []
  );

  const styledEdges = useMemo(
    () =>
      initialEdges.map((e) => ({
        ...e,
        type: "smoothstep",
        animated: e.animated || false,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: e.animated ? "#EF4444" : "#60A5FA",
        },
        style: {
          stroke: e.animated ? "#EF4444" : "#60A5FA",
          strokeWidth: e.animated ? 2.5 : 2,
          opacity: 0.9,
        },
      })),
    [initialEdges]
  );

  return (
    <div className={clsx("h-full w-full bg-[#0d1117] rounded-lg overflow-hidden", className)}>
      <ReactFlow
        nodes={nodes}
        edges={styledEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.5 }}
        minZoom={0.1}
        maxZoom={3}
        defaultEdgeOptions={{ type: "smoothstep" }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#30363d" gap={20} size={1} />
        <Controls className="!bg-[#161b22] !border-[#30363d] !rounded-lg !shadow-xl" />
        <MiniMap
          nodeColor={(node) => {
            const d = node.data as ModuleNodeData;
            if (d?.is_entry_point) return "#3B82F6";
            if (d?.is_hub) return "#8B5CF6";
            if (d?.is_orphan) return "#F59E0B";
            return "#6B7280";
          }}
          maskColor="#0d111780"
          className="!bg-[#161b22] !border-[#30363d] !rounded-lg"
        />

        {metadata && (
          <Panel position="top-left" className="!m-3">
            <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-3 text-xs text-gray-400 space-y-1 shadow-xl">
              <p className="text-white font-semibold text-sm mb-2">Dependency Graph</p>
              <p>📁 {metadata.total_files} files</p>
              <p>🔗 {metadata.total_edges} dependencies</p>
              {metadata.circular_count > 0 && (
                <p className="text-red-400">
                  ⚠ {metadata.circular_count} circular dep{metadata.circular_count > 1 ? "s" : ""}
                </p>
              )}
              {metadata.orphan_count > 0 && (
                <p className="text-amber-400">
                  📦 {metadata.orphan_count} orphan file{metadata.orphan_count > 1 ? "s" : ""}
                </p>
              )}
            </div>
          </Panel>
        )}

        {selectedNode && (
          <Panel position="top-right" className="!m-3">
            <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-3 text-xs text-gray-400 min-w-[180px] shadow-xl">
              <div className="flex items-center justify-between mb-2">
                <p className="text-white font-semibold">{selectedNode.label}</p>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="text-gray-500 hover:text-white text-lg leading-none"
                >
                  ×
                </button>
              </div>
              <p>📄 {selectedNode.file_path}</p>
              <p>💻 {selectedNode.language}</p>
              <p>→ Imports: {selectedNode.imports_count}</p>
              <p>← Imported by: {selectedNode.imported_by_count}</p>
              <p>Type: {selectedNode.node_type}</p>
            </div>
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}

export function DependencyGraphEmpty() {
  return (
    <div className="h-full flex flex-col items-center justify-center bg-[#0d1117] rounded-lg text-center p-8">
      <div className="text-5xl mb-4">🕸️</div>
      <h3 className="text-lg font-semibold text-white mb-2">No Dependencies Yet</h3>
      <p className="text-sm text-gray-400 max-w-sm">
        Upload multiple source files to see their import relationships visualized as an interactive graph.
      </p>
    </div>
  );
}