"use client";

import { useEffect } from "react";

/** 注册 service worker：让应用可离线、可安装为 PWA。 */
export function PwaRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // 注册失败不阻断应用（如本地开发或浏览器禁用 SW）。
      });
    }
  }, []);

  return null;
}
