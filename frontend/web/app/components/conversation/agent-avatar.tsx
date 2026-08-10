import { Bot, Loader2 } from "lucide-react";

type AgentAvatarProps = {
  loading?: boolean;
};

export function AgentAvatar({ loading = false }: AgentAvatarProps) {
  return (
    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center text-(--text-1)">
      {loading ? (
        <Loader2
          className="animate-spin text-(--accent)"
          size={22}
          aria-hidden="true"
        />
      ) : (
        <Bot className="text-(--text-1)" size={22} aria-hidden="true" />
      )}
    </div>
  );
}
