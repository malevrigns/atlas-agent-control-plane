import { Brain, Link2 } from "lucide-react";

import type { MemoryContext } from "../types";

const memoryKindLabels: Record<string, string> = {
  user_preference: "用户偏好",
  project_fact: "项目事实",
  task_experience: "任务经验",
  constraint: "长期约束",
};

// ===================== 第1步：展示本次真正注入的长期记忆 =====================
export function MemoryContextSection({
  memoryContext,
}: {
  memoryContext: MemoryContext;
}) {
  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-(--text-1)">
          <Brain size={16} aria-hidden="true" />
          长期记忆
        </h3>
        <span className="text-xs text-(--text-4)">
          {memoryContext.items.length}/{memoryContext.candidate_count} 条
        </span>
      </div>

      <p className="mt-2 text-xs leading-5 text-(--text-4)">
        已使用 {memoryContext.total_chars}/{memoryContext.max_chars} 字符预算
      </p>

      <div className="mt-3 grid gap-2">
        {memoryContext.items.length === 0 ? (
          <div className="rounded-md border border-dashed border-(--line) px-3 py-5 text-center text-sm text-(--text-4)">
            当前任务没有检索到可注入的长期记忆
          </div>
        ) : (
          memoryContext.items.map((memory) => (
            <article
              className="rounded-md border border-(--line) bg-(--fill-1) p-3"
              key={memory.id}
            >
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded bg-(--accent)/10 px-2 py-1 font-medium text-(--accent)">
                  {memoryKindLabels[memory.kind] ?? memory.kind}
                </span>
                <span className="text-(--text-4)">
                  相关度 {memory.relevance_score.toFixed(2)}
                </span>
                <span className="text-(--text-4)">
                  重要度 {memory.importance}
                </span>
              </div>

              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-(--text-2)">
                {memory.content}
              </p>

              {memory.matched_terms.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {memory.matched_terms.map((term) => (
                    <span
                      className="rounded border border-(--line) px-2 py-1 text-[11px] text-(--text-4)"
                      key={term}
                    >
                      {term}
                    </span>
                  ))}
                </div>
              ) : null}

              {memory.source_session_id ? (
                <div className="mt-3 flex items-center gap-1.5 text-[11px] text-(--text-5)">
                  <Link2 size={12} aria-hidden="true" />
                  来源会话 {memory.source_session_id.slice(0, 8)}
                </div>
              ) : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}
