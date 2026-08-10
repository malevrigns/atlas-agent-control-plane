/**
 * 数字滚动：value 变化时新值自下而上顶入（key 重挂载触发入场动画）。
 * 纯 CSS 实现，样式见 globals.css 的 .ticker / .ticker-value。
 */
export function NumberTicker({ value }: { value: number }) {
  return (
    <span aria-live="polite" className="ticker">
      <span className="ticker-value" key={value}>
        {value}
      </span>
    </span>
  );
}
