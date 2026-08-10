export const workspaceSurface = {
  panel:
    "border border-(--line) bg-(--fill-1) shadow-xl shadow-black/20",
  panelStrong:
    "border border-(--line) bg-(--surface)/95 shadow-2xl shadow-black/40",
  interactive:
    "transition hover:border-(--accent)/40 hover:bg-(--fill-2) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--accent)/60",
};

export const workspaceText = {
  heading: "font-semibold text-(--text-1)",
  body: "leading-7 text-(--text-3)",
  muted: "text-(--text-4)",
};

export const workspaceButton = {
  icon:
    "flex h-9 w-9 items-center justify-center rounded-full border border-(--line) bg-(--fill-1) text-(--text-4) transition hover:bg-(--fill-2) hover:text-(--text-1) disabled:cursor-not-allowed disabled:text-(--text-5)",
  primary:
    "bg-blue-500 text-white transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:bg-(--fill-3) disabled:text-(--text-4)",
};
