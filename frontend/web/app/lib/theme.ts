"use client";

import { useEffect, useState } from "react";

/** 主题偏好：跟随系统 / 亮色 / 暗色。持久化在 localStorage。 */
export type ThemePreference = "system" | "light" | "dark";

const STORAGE_KEY = "atlas-web-theme";

function isPreference(value: string | null): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function readThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return isPreference(saved) ? saved : "system";
}

function systemTheme(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function applyTheme(preference: ThemePreference) {
  const resolved = preference === "system" ? systemTheme() : preference;
  document.documentElement.dataset.theme = resolved;
}

/**
 * 主题偏好 Hook：返回当前偏好与设置函数。
 * 选择 system 时监听操作系统配色变化并实时跟随。
 */
export function useThemePreference(): [
  ThemePreference,
  (next: ThemePreference) => void,
] {
  const [preference, setPreference] = useState<ThemePreference>("system");

  useEffect(() => {
    const saved = readThemePreference();
    setPreference(saved);
    applyTheme(saved);
  }, []);

  useEffect(() => {
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => applyTheme("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  function update(next: ThemePreference) {
    setPreference(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  return [preference, update];
}
