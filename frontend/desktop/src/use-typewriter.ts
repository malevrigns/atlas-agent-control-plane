import { useEffect, useRef, useState } from "react";

type UseTypewriterOptions = {
  /** 基础显示速度（字符/秒）。 */
  charsPerSecond?: number;
  /** 落后真实流超过该字数后开始加速追赶，避免展示与实际进度脱节太远。 */
  catchUpThreshold?: number;
};

/**
 * 打字机节流：模型思考流往往瞬间灌入大段文本，直接渲染像刷屏。
 * 这里把已到达的文本按稳定速度逐字放出；落后太多时按差距加速追平。
 *
 * 实现要点：
 * - interval 常驻（仅随速度参数重建），tick 里经 ref 读最新文本——
 *   绝不能把 interval 挂在依赖 text 的 effect 上：流式 delta 每几十毫秒
 *   更新一次 text，定时器会被反复重建，永远活不到第一次触发。
 * - 用实际耗时 dt 推进而非固定步长：后台标签页定时器被钳制时，
 *   每次 tick 放出的字变多，整体速度仍稳定；dt 设上限避免深度
 *   节流唤醒后瞬间倾泻全部积压。
 * - 文本被清空（新一轮流开始）时立即重置。
 */
export function useTypewriter(
  text: string,
  { charsPerSecond = 45, catchUpThreshold = 400 }: UseTypewriterOptions = {},
) {
  const [visibleLength, setVisibleLength] = useState(0);
  const textRef = useRef(text);
  const progressRef = useRef(0);
  const lastTickRef = useRef(0);

  textRef.current = text;

  useEffect(() => {
    if (text.length < progressRef.current) {
      progressRef.current = 0;
      setVisibleLength(0);
    }
  }, [text]);

  useEffect(() => {
    lastTickRef.current = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const dt = Math.min((now - lastTickRef.current) / 1000, 2);
      lastTickRef.current = now;
      const full = textRef.current;
      if (progressRef.current >= full.length) {
        return;
      }
      const behind = full.length - progressRef.current;
      const rate = charsPerSecond + Math.max(0, behind - catchUpThreshold) * 2;
      progressRef.current = Math.min(
        full.length,
        progressRef.current + rate * dt,
      );
      setVisibleLength(Math.floor(progressRef.current));
    }, 50);
    return () => window.clearInterval(timer);
  }, [charsPerSecond, catchUpThreshold]);

  return text.slice(0, visibleLength);
}
