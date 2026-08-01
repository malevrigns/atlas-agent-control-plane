DEMO_TASKS = [
    {
        "id": "demo-task",
        "title": "重构 Agent Memory 与 Tool Runtime",
        "goal": "建立可验证、可失效、可追溯的记忆与工具控制平面",
        "status": "running",
        "version": 4,
        "state_hash": "sha256:a7f9c3d8b2e1f4a9",
        "requirements": [
            {"id": "REQ-001", "text": "不得把模型推测直接写入长期事实", "status": "active"},
        ],
        "progress": {"done": [{"text": "Memory 层"}], "doing": [{"text": "Tool Runtime"}], "blocked": []},
        "next_actions": [{"text": "运行兼容性测试"}],
    }
]

DEMO_CHECKPOINTS = [
    {"id": "CP-001", "kind": "full", "covered_event_start": 1, "covered_event_end": 48, "validator_report": {"valid": True}, "created_at": "2026-08-01T10:12:00Z"},
    {"id": "CP-002", "kind": "incremental", "covered_event_start": 49, "covered_event_end": 116, "validator_report": {"valid": True}, "created_at": "2026-08-01T10:47:00Z"},
    {"id": "CP-003", "kind": "incremental", "covered_event_start": 117, "covered_event_end": 181, "validator_report": {"valid": True}, "created_at": "2026-08-01T11:38:00Z"},
    {"id": "CP-004", "kind": "incremental", "covered_event_start": 182, "covered_event_end": 236, "validator_report": {"valid": True}, "created_at": "2026-08-01T12:28:00Z"},
]

DEMO_INVOCATIONS = [
    {"tool_name": "memory_search", "status": "succeeded", "risk_level": "low", "duration_ms": 42, "decision": "allow"},
    {"tool_name": "shell_run", "status": "approval_required", "risk_level": "high", "duration_ms": None, "decision": "require_approval"},
    {"tool_name": "file_read", "status": "succeeded", "risk_level": "low", "duration_ms": 18, "decision": "allow"},
]
