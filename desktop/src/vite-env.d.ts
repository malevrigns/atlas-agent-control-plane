/// <reference types="vite/client" />

import type { AtlasRequestOptions } from "./types";

interface AtlasDesktopBridge {
  readonly platform: string;
  readonly versions: {
    readonly chrome: string;
    readonly electron: string;
  };
  request<T>(path: string, options?: AtlasRequestOptions): Promise<T>;
}

declare global {
  interface Window {
    atlasDesktop?: AtlasDesktopBridge;
  }
}

export {};
