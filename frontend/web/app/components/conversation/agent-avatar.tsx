import { Bot, Loader2 } from "lucide-react";

type AgentAvatarProps = {
  loading?: boolean;
};

export function AgentAvatar({ loading = false }: AgentAvatarProps) {
  return (
    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center text-zinc-50">
      {loading ? (
        <Loader2
          className="animate-spin text-blue-400"
          size={22}
          aria-hidden="true"
        />
      ) : (
        <Bot className="text-zinc-50" size={22} aria-hidden="true" />
      )}
    </div>
  );
}
