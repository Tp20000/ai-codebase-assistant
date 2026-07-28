/**
 * Language Breakdown Pie Chart - Step 49
 * AI Codebase Assistant v2.0
 */

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

interface LanguageData {
  language: string;
  count: number;
}

interface LanguagePieChartProps {
  data: LanguageData[];
}

const LANG_COLORS: Record<string, string> = {
  python:     "#3776AB",
  javascript: "#F7DF1E",
  typescript: "#3178C6",
  java:       "#007396",
  go:         "#00ADD8",
  rust:       "#CE4A01",
  cpp:        "#659BD3",
  csharp:     "#239120",
  ruby:       "#CC342D",
  php:        "#777BB4",
  unknown:    "#6B7280",
};

export function LanguagePieChart({ data }: LanguagePieChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[var(--text-muted)]">
        No language data available
      </div>
    );
  }

  const chartData = data.map((d) => ({
    name: d.language.charAt(0).toUpperCase() + d.language.slice(1),
    value: d.count,
    color: LANG_COLORS[d.language.toLowerCase()] || LANG_COLORS.unknown,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={40}
          outerRadius={80}
          paddingAngle={2}
          dataKey="value"
          label={({ name, percent }) =>
            `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
          }
          labelLine={{ stroke: "#8b949e" }}
        >
          {chartData.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: "#161b22",
            border: "1px solid #30363d",
            borderRadius: 8,
            fontSize: 12,
            color: "#e6edf3",
          }}
          formatter={(value: unknown) => [`${value as number} files`, "Count"]}
        />
        <Legend
          wrapperStyle={{ fontSize: 11, color: "#8b949e" }}
          iconType="circle"
          iconSize={8}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}