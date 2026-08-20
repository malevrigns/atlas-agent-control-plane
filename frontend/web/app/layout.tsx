import type { Metadata, Viewport } from "next";
import Script from "next/script";

import { PwaRegister } from "./components/pwa-register";
import "./globals.css";

export const metadata: Metadata = {
  title: "AtlasAgent",
  description: "AtlasAgent workspace",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "AtlasAgent",
  },
};

export const viewport: Viewport = {
  themeColor: "#050506",
};

// 首帧前从 localStorage 恢复主题，避免亮色用户看到暗色闪烁。
// system 或未设置时跟随操作系统配色。
const themeInitScript = `(function(){try{var p=localStorage.getItem("atlas-web-theme");var t=p==="light"||p==="dark"?p:(window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme="dark";}})();`;

/* 滚动侦听：capture 捕获任意容器的 scroll，给该容器加 .is-scrolling，
   停止 650ms 后移除——配合 CSS 里可插值的滚动条变量实现点亮/熄灭动画。 */
const scrollGlowScript = `(function(){var timers=new WeakMap();document.addEventListener("scroll",function(e){var el=e.target===document?document.documentElement:e.target;if(!(el instanceof Element))return;el.classList.add("is-scrolling");var t=timers.get(el);if(t)clearTimeout(t);timers.set(el,setTimeout(function(){el.classList.remove("is-scrolling");},650));},{capture:true,passive:true});})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <Script id="atlas-theme-init" strategy="beforeInteractive">
          {themeInitScript}
        </Script>
        <Script id="atlas-scroll-glow" strategy="afterInteractive">
          {scrollGlowScript}
        </Script>
        <PwaRegister />
        {children}
      </body>
    </html>
  );
}
