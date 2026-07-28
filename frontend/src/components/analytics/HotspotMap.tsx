/**
 * File Hotspot Map - Step 49
 * AI Codebase Assistant v2.0
 *
 * Visual heatmap showing which files are most complex/large.
 */

import { clsx } from "clsx";

interface FileHotspot {
  file: string;
  lines: number;
  complexity: number;
  language: string;
}

interface HotspotMapProps {
  data: FileHotspot[];
}

function getHeatColor(value: number, max: number): string {
  const ratio = Math.min(1, value / Math.max(max, 1));
  if (ratio > 0.8) return "#DC2626";
  if (ratio > 0.6) return "#EF4444";
  if (ratio > 0.4) return "#F59E0B";
  if (ratio > 0.2) return "#10B981";
  return "#3B82F6";
}

export function HotspotMap({ data }: HotspotMapProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[var(--text-muted)]">
        No hotspot data available
      </div>
    );
  }

  const maxComplexity = Math.max(...data.map((d) => d.complexity), 1);
  const sorted = [...data].sort((a, b) => b.complexity - a.complexity).slice(0, 20);

  return (
    <div className="h-full overflow-y-auto p-2">
      <p className="text-xs text-[var(--text-muted)] mb-3">
        Files by complexity — darker = more complex
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        {sorted.map((file, i) => {
          const color = getHeatColor(file.complexity, maxComplexity);
          const fileName = file.file.split("/").pop() || file.file;

          return (
            <div
              key={i}
              className="relative rounded-lg p-2 border border-[var(--border)] overflow-hidden group cursor-default"
              style={{ backgroundColor: color + "20", borderColor: color + "40" }}
              title={`${file.file}\nLines: ${file.lines}\nComplexity: ${file.complexity}\nLanguage: ${file.language}`}
            >
              <div
                className="absolute inset-0 opacity-10"
                style={{ backgroundColor: color }}
              />
              <p className="relative text-[10px] font-semibold text-[var(--text-primary)] truncate">
                {fileName}
              </p>
              <p className="relative text-[9px] text-[var(--text-muted)]">
                CC: {file.complexity} · {file.lines} lines
              </p>
              <div
                className="absolute bottom-0 left-0 h-0.5 transition-all"
                style={{
                  width: `${(file.complexity / maxComplexity) * 100}%`,
                  backgroundColor: color,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex gap-3 mt-4 justify-center">
        {[
          { label: "Low", color: "#3B82F6" },
          { label: "Medium", color: "#10B981" },
          { label: "High", color: "#F59E0B" },
          { label: "Critical", color: "#EF4444" },
        ].map(({ label, color }) => (
          <span key={label} className="flex items-center gap-1 text-[9px] text-[var(--text-muted)]">
            <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: color }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}