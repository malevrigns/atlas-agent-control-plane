"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export type SelectMenuOption<T extends string> = {
  value: T;
  label: string;
  hint?: string;
};

type SelectMenuProps<T extends string> = {
  ariaLabel: string;
  value: T;
  options: Array<SelectMenuOption<T>>;
  onChange: (value: T) => void;
  /** 触发按钮的宽度类，默认自适应。 */
  className?: string;
};

/**
 * 与应用同一设计语言的自定义下拉，替代原生 select 的系统弹出层。
 * 支持点击外部与 Escape 关闭、选中标记与说明文字。
 */
export function SelectMenu<T extends string>({
  ariaLabel,
  value,
  options,
  onChange,
  className = "",
}: SelectMenuProps<T>) {
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
    <div className={`relative ${className}`} ref={rootRef}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`${ariaLabel}：${active?.label ?? ""}`}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-xl border border-(--line) bg-(--field) px-3 text-sm text-(--text-1) transition hover:border-(--line-strong)"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span className="truncate">{active?.label}</span>
        <ChevronDown
          aria-hidden="true"
          className={`shrink-0 text-(--text-4) transition-transform ${open ? "rotate-180" : ""}`}
          size={14}
        />
      </button>
      {open ? (
        <div
          aria-label={ariaLabel}
          className="absolute left-0 top-11 z-50 max-h-72 w-full min-w-40 overflow-y-auto rounded-2xl border border-(--line) bg-(--surface-2)/95 p-1.5 shadow-2xl shadow-black/30 backdrop-blur-xl"
          role="listbox"
        >
          {options.map((option) => {
            const selected = option.value === value;
            return (
              <button
                aria-selected={selected}
                className={`flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-sm transition ${
                  selected
                    ? "bg-(--accent)/12 text-(--text-1)"
                    : "text-(--text-3) hover:bg-(--fill-1) hover:text-(--text-1)"
                }`}
                key={option.value}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                role="option"
                type="button"
              >
                <span className="min-w-0">
                  <span className="block truncate">{option.label}</span>
                  {option.hint ? (
                    <span className="mt-0.5 block text-xs text-(--text-4)">{option.hint}</span>
                  ) : null}
                </span>
                {selected ? (
                  <Check className="shrink-0 text-(--accent)" size={14} aria-hidden="true" />
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
