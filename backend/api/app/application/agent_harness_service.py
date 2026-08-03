from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

from app.core.exceptions import AppException
from app.domain.harness.entities import (
    HarnessAssertion,
    HarnessCase,
    HarnessExpectation,
    HarnessRun,
)


class AgentHarnessService:
    """运行 Agent 回归评测任务集。

    Harness 的目标不是替代人工验收，而是把“每次重构后最容易坏的核心链路”
    固定成可重复运行的任务集。第 45 章先提供稳定的 simulate 模式，
    后续可以把 real 模式接到真实 Agent Runner 上。
    """

    def __init__(self, case_file: Path | None = None) -> None:
        # ===================== 第1步：确定评测任务集文件 =====================
        api_root = Path(__file__).resolve().parents[2]
        self.case_file = case_file or api_root / "config" / "eval_cases.yaml"

        # ===================== 第2步：准备进程内运行结果存储 =====================
        # 本章先不新增数据库表，避免为了教学 Harness 引入迁移负担。
        # API 重启后历史运行记录会丢失，这是当前阶段可以接受的。
        self._runs: dict[str, HarnessRun] = {}

    def list_cases(self) -> list[HarnessCase]:
        """读取本地评测任务集。"""

        raw = self._load_case_document()
        return [self._parse_case(item) for item in raw.get("cases", [])]

    def get_case(self, case_id: str) -> HarnessCase:
        """根据 case_id 查找一条评测用例。"""

        for case in self.list_cases():
            if case.id == case_id:
                return case
        raise AppException(
            message="harness case not found",
            code=404,
            status_code=404,
        )

    def run_case(self, case_id: str, mode: str = "simulate") -> HarnessRun:
        """运行单条 Harness 用例。

        第 45 章默认只支持 simulate 模式。它会生成一组符合用例预期的事件，
        用来验证 Harness 的断言、回放和前端展示链路。真实模型运行模式会在后续章节
        复用同一份 `evaluate_events()` 断言逻辑。
        """

        # ===================== 第1步：读取用例并校验运行模式 =====================
        case = self.get_case(case_id)
        if mode != "simulate":
            raise AppException(
                message="only simulate mode is available in this chapter",
                code=400,
                status_code=400,
            )

        # ===================== 第2步：生成稳定事件流 =====================
        started_at = self._now()
        events = self._simulate_events(case)

        # ===================== 第3步：对事件流执行断言 =====================
        assertions = self.evaluate_events(case, events)
        passed = all(assertion.passed for assertion in assertions)
        completed_at = self._now()

        # ===================== 第4步：保存运行结果，供失败回放接口读取 =====================
        run = HarnessRun(
            id=str(uuid4()),
            case_id=case.id,
            mode=mode,
            status="passed" if passed else "failed",
            task=case.task,
            prompt_summary=self._build_prompt_summary(case),
            events=events,
            assertions=assertions,
            started_at=started_at,
            completed_at=completed_at,
        )
        self._runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> HarnessRun:
        """读取一次 Harness 运行结果。"""

        run = self._runs.get(run_id)
        if run is None:
            raise AppException(
                message="harness run not found",
                code=404,
                status_code=404,
            )
        return run

    def replay_run(self, run_id: str) -> HarnessRun:
        """返回一次运行的完整事件流，用于前端回放。"""

        return self.get_run(run_id)

    def evaluate_events(
        self,
        case: HarnessCase,
        events: list[dict],
    ) -> list[HarnessAssertion]:
        """对一组事件执行 Harness 断言。

        这里刻意只依赖事件字典，不依赖数据库模型或 HTTP 响应模型。
        这样真实 Runner、模拟 Runner、测试 fixture 都能复用同一套断言逻辑。
        """

        # ===================== 第1步：抽取事件类型、工具名和产物名 =====================
        event_types = {str(event.get("type")) for event in events}
        tool_names = {
            str(event.get("payload", {}).get("tool_name"))
            for event in events
            if event.get("type") == "tool_called"
        }
        file_names = {
            str(event.get("payload", {}).get("file_name"))
            for event in events
            if event.get("type") == "file_created"
        }

        # ===================== 第2步：逐类规则生成断言结果 =====================
        assertions: list[HarnessAssertion] = []
        assertions.extend(
            self._assert_contains(
                name="required_event",
                expected=case.expectation.required_events,
                actual=event_types,
            )
        )
        assertions.extend(
            self._assert_contains(
                name="required_tool",
                expected=case.expectation.required_tools,
                actual=tool_names,
            )
        )
        assertions.extend(
            self._assert_contains(
                name="required_file",
                expected=case.expectation.required_files,
                actual=file_names,
            )
        )
        assertions.extend(
            self._assert_absent(
                name="forbidden_event",
                expected_absent=case.expectation.forbidden_events,
                actual=event_types,
            )
        )
        return assertions

    def _load_case_document(self) -> dict:
        if not self.case_file.exists():
            raise AppException(
                message=f"harness case file not found: {self.case_file}",
                code=500,
                status_code=500,
            )
        with self.case_file.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
        if not isinstance(loaded, dict):
            raise AppException(
                message="harness case file must be a YAML object",
                code=500,
                status_code=500,
            )
        return loaded

    def _parse_case(self, item: dict) -> HarnessCase:
        expectation = item.get("expectation") or {}
        return HarnessCase(
            id=str(item["id"]),
            title=str(item["title"]),
            task=str(item["task"]),
            description=str(item.get("description") or ""),
            tags=[str(tag) for tag in item.get("tags", [])],
            expectation=HarnessExpectation(
                required_events=[
                    str(value) for value in expectation.get("required_events", [])
                ],
                required_tools=[
                    str(value) for value in expectation.get("required_tools", [])
                ],
                required_files=[
                    str(value) for value in expectation.get("required_files", [])
                ],
                forbidden_events=[
                    str(value) for value in expectation.get("forbidden_events", [])
                ],
            ),
        )

    def _simulate_events(self, case: HarnessCase) -> list[dict]:
        """生成一组稳定事件，模拟真实 Agent 运行过程。"""

        base_time = self._now().isoformat()
        events: list[dict] = [
            self._event(
                event_type="message_created",
                created_at=base_time,
                payload={"role": "user", "content": case.task},
            ),
            self._event(
                event_type="plan_created",
                created_at=base_time,
                payload={
                    "title": case.title,
                    "goal": case.task,
                    "source": "harness_simulate",
                },
            ),
        ]

        for tool_name in case.expectation.required_tools:
            events.append(
                self._event(
                    event_type="tool_called",
                    created_at=base_time,
                    payload={
                        "tool_name": tool_name,
                        "arguments": {"case_id": case.id},
                        "observation": f"{tool_name} completed in simulate mode.",
                    },
                )
            )

        for file_name in case.expectation.required_files:
            events.append(
                self._event(
                    event_type="file_created",
                    created_at=base_time,
                    payload={"file_name": file_name},
                )
            )

        for event_type in case.expectation.required_events:
            if event_type not in {event["type"] for event in events}:
                events.append(
                    self._event(
                        event_type=event_type,
                        created_at=base_time,
                        payload={"case_id": case.id, "simulated": True},
                    )
                )

        return events

    def _event(self, event_type: str, created_at: str, payload: dict) -> dict:
        return {
            "id": str(uuid4()),
            "type": event_type,
            "payload": payload,
            "created_at": created_at,
        }

    def _assert_contains(
        self,
        *,
        name: str,
        expected: list[str],
        actual: set[str],
    ) -> list[HarnessAssertion]:
        assertions: list[HarnessAssertion] = []
        for value in expected:
            passed = value in actual
            assertions.append(
                HarnessAssertion(
                    name=f"{name}:{value}",
                    passed=passed,
                    detail=(
                        f"found {value}"
                        if passed
                        else f"missing {value}; actual={sorted(actual)}"
                    ),
                )
            )
        return assertions

    def _assert_absent(
        self,
        *,
        name: str,
        expected_absent: list[str],
        actual: set[str],
    ) -> list[HarnessAssertion]:
        assertions: list[HarnessAssertion] = []
        for value in expected_absent:
            passed = value not in actual
            assertions.append(
                HarnessAssertion(
                    name=f"{name}:{value}",
                    passed=passed,
                    detail=(
                        f"{value} is absent"
                        if passed
                        else f"{value} should be absent"
                    ),
                )
            )
        return assertions

    def _build_prompt_summary(self, case: HarnessCase) -> str:
        return (
            f"case={case.id}; task={case.task}; "
            f"required_events={','.join(case.expectation.required_events)}; "
            f"required_tools={','.join(case.expectation.required_tools)}"
        )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
