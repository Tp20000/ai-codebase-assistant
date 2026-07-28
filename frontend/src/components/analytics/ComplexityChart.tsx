/**
 * Complexity Chart - Step 49
 * AI Codebase Assistant v2.0
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface FileComplexity {
  file: string;
  avg_cyclomatic: number;
  max_cyclomatic: number;
  maintainability_index: number;
  grade: string;
  total_lines: number;
}

interface ComplexityChartProps {
  data: FileComplexity[];
  metric?: "avg_cyclomatic" | "max_cyclomatic" | "maintainability_index";
}

const GRADE_COLORS: Record<string, string> = {
  A: "#10B981",
  B: "#3B82F6",
  C: "#F59E0B",
  D: "#EF4444",
  F: "#DC2626",
};

function getColor(grade: string): string {
  return GRADE_COLORS[grade] || "#6B7280";
}

export function ComplexityChart({
  data,
  metric = "max_cyclomatic",
}: ComplexityChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[var(--text-muted)]">
        No complexity data available
      </div>
    );
  }

  const chartData = data
    .sort((a, b) => b[metric] - a[metric])
    .slice(0, 15)
    .map((d) => ({
      name: d.file.split("/").pop() || d.file,
      value: d[metric],
      grade: d.grade,
      fullPath: d.file,
    }));

  const labels: Record<string, string> = {
    avg_cyclomatic: "Avg Cyclomatic Complexity",
    max_cyclomatic: "Max Cyclomatic Complexity",
    maintainability_index: "Maintainability Index",
  };

  return (
    <div className="h-full w-full">
      <p className="text-xs text-[var(--text-muted)] mb-2 px-2">
        {labels[metric]} — Top 15 Files
      </p>
      <ResponsiveContainer width="100%" height="90%">
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
          <XAxis type="number" tick={{ fill: "#8b949e", fontSize: 10 }} />
          <YAxis
            dataKey="name"
            type="category"
            tick={{ fill: "#e6edf3", fontSize: 10 }}
            width={75}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#161b22",
              border: "1px solid #30363d",
              borderRadius: 8,
              fontSize: 12,
              color: "#e6edf3",
            }}
            formatter={((value: unknown, _: unknown, props: { payload?: { fullPath: string; grade: string } }) => [
              `${value} (Grade ${props.payload.grade})`,
              labels[metric],
            ]) as never}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={index} fill={getColor(entry.grade)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}