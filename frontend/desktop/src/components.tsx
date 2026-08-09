import { CirclesFour } from "@phosphor-icons/react";
import type { Dispatch, SetStateAction } from "react";
import type { Theme } from "./types";

export const themeOptions: Array<{ value: Theme; label: string }> = [
  { value: "ink", label: "墨夜" },
  { value: "dawn", label: "晨光" },
  { value: "contrast", label: "高对比" },
];

interface ThemeSelectProps {
  theme: Theme;
  onChange: Dispatch<SetStateAction<Theme>>;
}

export function ThemeSelect({ theme, onChange }: ThemeSelectProps) {
  return (
    <label className="theme-control">
      <CirclesFour size={17} weight="regular" aria-hidden="true" />
      <span className="sr-only">选择主题</span>
      <select
        value={theme}
        onChange={(event) => onChange(event.target.value as Theme)}
        aria-label="选择界面主题"
      >
        {themeOptions.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

interface NoticeProps {
  notice: string;
  tone?: "info" | "danger";
}

export function InlineNotice({ notice, tone = "info" }: NoticeProps) {
  if (!notice) return null;
  return (
    <div className={`inline-notice ${tone}`} role="status">
      {notice}
    </div>
  );
}

export function formatTimestamp(value: string | null): string {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "时间未知"
    : date.toLocaleString("zh-CN", { hour12: false });
}
