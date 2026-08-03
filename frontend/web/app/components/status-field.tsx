export function StatusField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 min-h-5 truncate text-sm font-medium text-slate-900">
        {value}
      </div>
    </div>
  );
}
