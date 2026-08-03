import os
from datetime import datetime
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog, Select, Static

from atlas_agent_tui.api import AtlasApiClient
from atlas_agent_tui.demo import DEMO_CHECKPOINTS, DEMO_INVOCATIONS, DEMO_TASKS


class AtlasTui(App):
    TITLE = "AtlasAgent Control Plane"
    SUB_TITLE = "Memory · Checkpoints · Tool Runtime"
    CSS = """
    Screen { background: $surface; color: $text; }
    #connection { dock: top; height: 1; padding: 0 2; color: $text-muted; background: $panel; }
    #body { height: 1fr; }
    #tasks { width: 32; min-width: 24; border-right: solid $primary-background; }
    #main { width: 1fr; padding: 0 1; }
    #audit { width: 40; min-width: 30; border-left: solid $primary-background; }
    .panel-title { height: 3; padding: 1 1 0 1; color: $text; text-style: bold; }
    ListView { height: 1fr; }
    ListItem { padding: 1 1; }
    ListItem.--highlight { background: $primary-background; color: $text; }
    #task-summary { height: auto; min-height: 7; padding: 1 2; border: round $primary; }
    #checkpoints { height: 1fr; margin-top: 1; }
    #prompt-row { dock: bottom; height: 3; }
    #prompt { width: 1fr; }
    #policy { width: 22; }
    RichLog { scrollbar-size: 1 1; padding: 0 1; }
    .ok { color: $success; }
    .warn { color: $warning; }
    .bad { color: $error; }
    """
    BINDINGS = [
        ("q", "quit", "退出"),
        ("r", "refresh", "刷新"),
        ("n", "new_session", "新会话"),
        ("slash", "focus_prompt", "输入"),
        ("t", "toggle_theme", "主题"),
        ("1", "focus_tasks", "任务"),
        ("2", "focus_checkpoints", "检查点"),
        ("3", "focus_audit", "审计"),
    ]

    def __init__(self) -> None:
        super().__init__()
        base_url = os.getenv("ATLAS_API_URL", "http://localhost:8088")
        self.api = AtlasApiClient(base_url, api_key=os.getenv("ATLAS_API_KEY", ""))
        self.sessions: list[dict[str, Any]] = []
        self.tasks: list[dict[str, Any]] = []
        self.checkpoints: list[dict[str, Any]] = []
        self.invocations: list[dict[str, Any]] = []
        self.selected_session_id: str | None = None
        self.demo_mode = False
        self.creating_session = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("正在连接 AtlasAgent…", id="connection")
        with Horizontal(id="body"):
            with Vertical(id="tasks"):
                yield Label("任务", classes="panel-title")
                yield ListView(id="task-list")
            with Vertical(id="main"):
                yield Label("检查点时间线", classes="panel-title")
                yield Static("选择任务以查看状态", id="task-summary")
                yield RichLog(id="checkpoints", wrap=True, markup=True)
                with Horizontal(id="prompt-row"):
                    yield Input(placeholder="输入任务指令；/ 聚焦，Enter 发送", id="prompt")
                    yield Select(
                        [("自动允许低/中风险", "medium"), ("仅低风险", "low"), ("全部询问", "ask")],
                        value="medium",
                        id="policy",
                        allow_blank=False,
                    )
            with Vertical(id="audit"):
                yield Label("工具审计", classes="panel-title")
                yield RichLog(id="audit-log", wrap=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "textual-dark"
        self.refresh_data()

    @work(exclusive=True, group="refresh")
    async def refresh_data(self) -> None:
        connection = self.query_one("#connection", Static)
        try:
            await self.api.status()
            self.sessions = await self.api.sessions()
            if self.sessions and not self.selected_session_id:
                self.selected_session_id = str(self.sessions[0]["id"])
            self.tasks = await self.api.tasks()
            self.invocations = await self.api.tool_invocations()
            self.demo_mode = False
            connection.update(f"[green]● 已连接[/green]  {self.api.base_url}  ·  r 刷新  ·  t 切换主题")
        except Exception as error:
            self.tasks = DEMO_TASKS
            self.checkpoints = DEMO_CHECKPOINTS
            self.invocations = DEMO_INVOCATIONS
            self.demo_mode = True
            connection.update(f"[yellow]● 演示数据模式[/yellow]  {type(error).__name__}  ·  启动 API 后按 r 重连")
        self._render_tasks()
        await self._select_task(0)
        self._render_audit()

    def _render_tasks(self) -> None:
        task_list = self.query_one("#task-list", ListView)
        task_list.clear()
        for task in self.tasks:
            status = task.get("status", "pending")
            task_list.append(ListItem(Label(f"{task.get('title', '未命名任务')}\n[{status}] v{task.get('version', 1)}")))
        if not self.tasks:
            task_list.append(ListItem(Label("暂无控制平面任务"), disabled=True))

    @on(ListView.Selected, "#task-list")
    async def select_task(self, event: ListView.Selected) -> None:
        await self._select_task(event.list_view.index or 0)

    async def _select_task(self, index: int) -> None:
        if not self.tasks:
            return
        index = max(0, min(index, len(self.tasks) - 1))
        task = self.tasks[index]
        if not self.demo_mode:
            try:
                self.checkpoints = await self.api.checkpoints(str(task["id"]))
            except Exception:
                self.checkpoints = []
        summary = self.query_one("#task-summary", Static)
        progress = task.get("progress") or {}
        summary.update(
            f"[b]{task.get('title')}[/b]\n"
            f"{task.get('goal', '')}\n"
            f"状态 [cyan]{task.get('status')}[/cyan] · 版本 {task.get('version', 1)} · "
            f"完成 {len(progress.get('done', []))} / 进行 {len(progress.get('doing', []))} / 阻塞 {len(progress.get('blocked', []))}\n"
            f"Hash {task.get('state_hash', '-') }"
        )
        self._render_checkpoints()

    def _render_checkpoints(self) -> None:
        log = self.query_one("#checkpoints", RichLog)
        log.clear()
        if not self.checkpoints:
            log.write("[dim]尚无 Checkpoint。阶段切换、高风险操作前或事件达到阈值时会生成。[/dim]")
            return
        for item in reversed(self.checkpoints):
            valid = bool((item.get("validator_report") or {}).get("valid"))
            marker = "[green]●[/green]" if valid else "[red]×[/red]"
            created = str(item.get("created_at") or "")
            if created:
                try:
                    created = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%H:%M")
                except ValueError:
                    pass
            log.write(
                f"{marker} [b]{item.get('id')}[/b]  {created}  "
                f"事件 {item.get('covered_event_start')}–{item.get('covered_event_end')}  "
                f"{item.get('kind')}  {'已验证，可恢复' if valid else '验证失败'}"
            )

    def _render_audit(self) -> None:
        log = self.query_one("#audit-log", RichLog)
        log.clear()
        if not self.invocations:
            log.write("[dim]暂无工具调用。[/dim]")
            return
        for item in self.invocations:
            status = str(item.get("status"))
            color = "green" if status in {"succeeded", "deduplicated"} else "yellow" if status == "approval_required" else "red"
            duration = f"{item.get('duration_ms')} ms" if item.get("duration_ms") is not None else "—"
            log.write(
                f"[{color}]●[/{color}] [b]{item.get('tool_name')}[/b]\n"
                f"  {status} · {item.get('risk_level')} · {item.get('decision')} · {duration}"
            )

    @on(Input.Submitted, "#prompt")
    def submit_prompt(self, event: Input.Submitted) -> None:
        content = event.value.strip()
        if not content:
            return
        event.input.clear()
        if self.creating_session:
            self.create_session(content)
            return
        self.send_message(content)

    @work(exclusive=True, group="create-session")
    async def create_session(self, title: str) -> None:
        connection = self.query_one("#connection", Static)
        try:
            session = await self.api.create_session(title)
            self.selected_session_id = str(session["id"])
            self.creating_session = False
            self.query_one("#prompt", Input).placeholder = "输入任务指令；/ 聚焦，Enter 发送"
            connection.update(f"[green]● 会话已创建[/green]  {title}")
            self.refresh_data()
        except Exception as error:
            connection.update(f"[red]创建会话失败[/red]  {error}")

    @work(exclusive=True, group="send")
    async def send_message(self, content: str) -> None:
        connection = self.query_one("#connection", Static)
        if not self.selected_session_id:
            if self.sessions:
                self.selected_session_id = str(self.sessions[0]["id"])
            else:
                connection.update("[yellow]没有可用会话；按 n 后输入标题并回车创建。[/yellow]")
                return
        connection.update("[cyan]● 正在执行[/cyan]  已发送指令，等待事件流…")
        try:
            async for event in self.api.stream_message(self.selected_session_id, content):
                name = event.get("event")
                if name in {"tool_called", "task_done", "task_error", "step_completed"}:
                    self.query_one("#audit-log", RichLog).write(f"[dim]{name}[/dim] {event.get('data', {})}")
            self.refresh_data()
        except Exception as error:
            connection.update(f"[red]执行失败[/red]  {error}")

    def action_refresh(self) -> None:
        self.refresh_data()

    def action_focus_prompt(self) -> None:
        self.query_one("#prompt", Input).focus()

    def action_focus_tasks(self) -> None:
        self.query_one("#task-list", ListView).focus()

    def action_focus_checkpoints(self) -> None:
        self.query_one("#checkpoints", RichLog).focus()

    def action_focus_audit(self) -> None:
        self.query_one("#audit-log", RichLog).focus()

    def action_toggle_theme(self) -> None:
        themes = ["textual-dark", "textual-light", "nord"]
        current = themes.index(self.theme) if self.theme in themes else 0
        self.theme = themes[(current + 1) % len(themes)]

    def action_new_session(self) -> None:
        self.creating_session = True
        prompt = self.query_one("#prompt", Input)
        prompt.placeholder = "输入新会话标题并回车创建"
        prompt.focus()


def main() -> None:
    AtlasTui().run()
