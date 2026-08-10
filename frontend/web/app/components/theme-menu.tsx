"use client";

import { Check, ChevronDown, Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useThemePreference } from "../lib/theme";
import type { ThemePreference } from "../lib/theme";

const OPTIONS: Array<{
  value: ThemePreference;
  label: string;
  hint: string;
  icon: typeof Sun;
}> = [
  { value: "system", label: "跟随系统", hint: "随操作系统自动切换", icon: Monitor },
  { value: "light", label: "亮色", hint: "明亮环境下使用", icon: Sun },
  { value: "dark", label: "暗色", hint: "默认的深色工作台", icon: Moon },
];

/**
 * 自定义主题下拉：替代原生 select，展开列表与应用同一套设计语言。
 * 支持点击外部与 Escape 关闭，选项带图标、说明和选中标记。
 */
export function ThemeMenu() {
  const [preference, setPreference] = useThemePreference();
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

  const active = OPTIONS.find((option) => option.value === preference) ?? OPTIONS[0];
  const ActiveIcon = active.icon;

  return (
    <div className="relative" ref={rootRef}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`界面主题：${active.label}`}
        className="flex h-8 items-center gap-1.5 rounded-full px-2.5 text-(--text-4) transition hover:bg-(--fill-2) hover:text-(--text-1)"
        onClick={() => setOpen((value) => !value)}
        title="界面主题"
        type="button"
      >
        <ActiveIcon size={15} aria-hidden="true" />
        <ChevronDown
          aria-hidden="true"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
          size={13}
        />
      </button>
      {open ? (
        <div
          className="absolute right-0 top-10 z-50 w-52 overflow-hidden rounded-2xl border border-(--line) bg-(--surface-2)/95 p-1.5 shadow-2xl shadow-black/30 backdrop-blur-xl"
          role="listbox"
          aria-label="选择界面主题"
        >
          {OPTIONS.map((option) => {
            const OptionIcon = option.icon;
            const selected = option.value === preference;
            return (
              <button
                aria-selected={selected}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition ${
                  selected
                    ? "bg-(--accent)/12 text-(--text-1)"
                    : "text-(--text-3) hover:bg-(--fill-1) hover:text-(--text-1)"
                }`}
                key={option.value}
                onClick={() => {
                  setPreference(option.value);
                  setOpen(false);
                }}
                role="option"
                type="button"
              >
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-(--line) ${
                    selected ? "bg-(--accent)/15 text-(--accent)" : "bg-(--fill-1)"
                  }`}
                >
                  <OptionIcon size={15} aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{option.label}</span>
                  <span className="mt-0.5 block text-xs text-(--text-4)">{option.hint}</span>
                </span>
                {selected ? (
                  <Check className="shrink-0 text-(--accent)" size={15} aria-hidden="true" />
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
