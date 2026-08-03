export function TaskFlowPreview() {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <h2 className="text-base font-semibold text-slate-950">任务流预览</h2>
      <div className="mt-4 grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
        {["创建会话", "发送任务", "Agent 执行", "事件展示"].map(
          (label, index) => (
            <div
              key={label}
              className={`rounded-md border px-4 py-3 ${
                index === 0
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              <div className="text-xs text-slate-500">Step {index + 1}</div>
              <div className="mt-2 text-sm font-medium text-slate-800">
                {label}
              </div>
            </div>
          ),
        )}
      </div>
    </section>
  );
}
