import type { StatusBadgeView } from "../types";

export function StatusBadge({ badge }: { badge: StatusBadgeView }) {
  const Icon = badge.icon;
  return (
    <div
      className={`flex h-9 items-center gap-2 rounded-md border px-3 text-sm ${badge.className}`}
    >
      <Icon size={16} aria-hidden="true" />
      <span>{badge.label}</span>
    </div>
  );
}
