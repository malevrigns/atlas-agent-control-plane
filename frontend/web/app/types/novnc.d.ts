declare module "@novnc/novnc" {
  export default class RFB extends EventTarget {
    scaleViewport: boolean;
    resizeSession: boolean;
    viewOnly: boolean;

    constructor(target: HTMLElement, url: string);
    disconnect(): void;
  }
}
