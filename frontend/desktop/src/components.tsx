import { CaretDown, Check, CirclesFour } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { Theme } from "./types";

// ===================== 自定义下拉 =====================

export interface DropdownOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

interface DropdownProps<T extends string> {
  ariaLabel: string;
  value: T;
  options: Array<DropdownOption<T>>;
  onChange: (value: T) => void;
  /** 触发按钮左侧的图标。 */
  icon?: ReactNode;
  /** 收起时是否隐藏当前值文字（紧凑模式只显示图标）。 */
  compact?: boolean;
}

/**
 * 与桌面端设计体系一致的自定义下拉，替代原生 select 的系统弹出层。
 * 支持点击外部关闭、Escape 关闭、选中标记与说明文字。
 */
export function Dropdown<T extends string>({
  ariaLabel,
  value,
  options,
  onChange,
  icon,
  compact = false,
}: DropdownProps<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const active = options.find((option) => option.value === value) ?? options[0];

  return (
    <div className="dropdown" ref={rootRef}>
      <button
        type="button"
        className="dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${ariaLabel}：${active.label}`}
        onClick={() => setOpen((current) => !current)}
      >
        {icon}
        {compact ? null : <span className="dropdown-value">{active.label}</span>}
        <CaretDown size={13} className={`dropdown-caret ${open ? "open" : ""}`} />
      </button>
      {open ? (
        <div className="dropdown-menu" role="listbox" aria-label={ariaLabel}>
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              className={`dropdown-item ${option.value === value ? "selected" : ""}`}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              <span className="dropdown-item-text">
                <strong>{option.label}</strong>
                {option.hint ? <small>{option.hint}</small> : null}
              </span>
              {option.value === value ? <Check size={14} weight="bold" /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ===================== 主题选择 =====================

export const themeOptions: Array<DropdownOption<Theme>> = [
  { value: "ink", label: "墨夜", hint: "近黑底 · 冷蓝强调" },
  { value: "dawn", label: "晨光", hint: "浅色背景 · 明亮环境" },
  { value: "contrast", label: "高对比", hint: "强化边界与焦点" },
];

interface ThemeSelectProps {
  theme: Theme;
  onChange: Dispatch<SetStateAction<Theme>>;
}

export function ThemeSelect({ theme, onChange }: ThemeSelectProps) {
  return (
    <Dropdown
      ariaLabel="界面主题"
      icon={<CirclesFour size={16} weight="regular" aria-hidden="true" />}
      value={theme}
      options={themeOptions}
      onChange={(value) => onChange(value)}
    />
  );
}

// ===================== 通用小组件 =====================

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
