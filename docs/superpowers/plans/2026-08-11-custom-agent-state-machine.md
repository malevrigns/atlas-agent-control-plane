# Custom Agent State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace AtlasAgent's unconditional linear step completion with a framework-free, typed Execute/Reflect state machine and strict Critic protocol.

**Architecture:** Keep Planner, Memory, RAG, ToolRuntime, and Session SSE intact. Add immutable runtime state plus a pure router, then make ReAct expose a status-aware single-step result and drive that result through Critic decisions before a step can complete. The synchronous execution API will collect the same stream used by SSE so there is one orchestration path.

**Tech Stack:** Python 3.11+, dataclasses, StrEnum, asyncio, unittest, existing FastAPI/SQLAlchemy application services.

## Global Constraints

- Do not add LangGraph, LangChain, or another agent orchestration framework.
- Do not add SHA-256, state hashes, schema hashes, or hash verification.
- Do not add silent fallbacks, swallowed protocol errors, fake success, or model-output repair.
- Keep direct chat, Memory, RAG, ToolRuntime, and existing plan payloads compatible.
- Production functions stay at or below 50 lines; production files stay at or below 300 lines.
- Follow test-first RED -> GREEN -> REFACTOR for every behavior change.

---

### Task 1: Immutable Agent Runtime State and Router

**Files:**
- Create: `backend/api/app/domain/agent_runtime/__init__.py`
- Create: `backend/api/app/domain/agent_runtime/entities.py`
- Create: `backend/api/app/domain/agent_runtime/router.py`
- Test: `backend/api/tests/test_agent_state_machine.py`

**Interfaces:**
- Produces: `AgentPhase`, `ReflectionAction`, `RunPlanStep`, `RunPlan`, `StepObservation`, `Reflection`, `AgentRunState`.
- Produces: `AgentStateRouter.after_execution(state, observation)`, `after_reflection(state, reflection)`, and `after_summary(state, final_answer)`.
- `AgentRunState.from_plan(session_id: UUID, plan_payload: dict[str, object])` creates an executing state with zero-based `step_index=0` and `attempt=1`.

- [ ] **Step 1: Write failing transition tests**

Add `test_agent_state_machine.py` with focused tests for:

```python
state = AgentRunState.from_plan(session_id, plan_payload())
reflecting = router.after_execution(state, observation("succeeded"))
self.assertEqual(reflecting.phase, AgentPhase.reflecting)

next_step = router.after_reflection(
    reflecting,
    Reflection(action=ReflectionAction.accept, reason="evidence matches"),
)
self.assertEqual(next_step.step_index, 1)
self.assertEqual(next_step.phase, AgentPhase.executing)
```

Also assert last-step accept -> summarizing, retry keeps the same step and increments attempt, replan -> replanning, fail -> failed, approval_required -> blocked, deduplicated is accepted as a successful observation, and pending/running raise `ValueError`.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest tests.test_agent_state_machine -v
```

Expected: import failure because `app.domain.agent_runtime` does not exist.

- [ ] **Step 3: Implement immutable entities and pure transitions**

Implement frozen, slotted dataclasses. Convert plan payload steps into immutable `RunPlanStep` tuples. Router methods use `dataclasses.replace`; they do not perform IO or mutate input values.

Terminal mapping must be exact:

```python
SUCCESS_STATUSES = {
    ToolInvocationStatus.succeeded,
    ToolInvocationStatus.deduplicated,
}
FINAL_FAILURE_STATUSES = {
    ToolInvocationStatus.failed,
    ToolInvocationStatus.timed_out,
    ToolInvocationStatus.denied,
}
```

- [ ] **Step 4: Run focused and full tests**

Run:

```powershell
python -m unittest tests.test_agent_state_machine -v
python -m unittest discover -s tests -v
```

Expected: new tests pass and the existing suite remains green.

- [ ] **Step 5: Commit**

```powershell
git add backend/api/app/domain/agent_runtime backend/api/tests/test_agent_state_machine.py
git commit -m "feat: add typed agent execution state machine"
```

### Task 2: Status-Aware ReAct Step Execution

**Files:**
- Modify: `backend/api/app/domain/sessions/entities.py`
- Create: `backend/api/app/application/react_step_executor.py`
- Modify: `backend/api/app/application/react_agent_service.py`
- Create: `backend/api/tests/test_step_failure_semantics.py`

**Interfaces:**
- Consumes: `StepObservation` and success/failure status sets from Task 1.
- Produces: `StepExecutionOutcome(events: tuple[SessionEvent, ...], observation: StepObservation)`.
- Produces: `ReActStepExecutor.execute(request: StepExecutionRequest) -> StepExecutionOutcome`.
- `StepExecutionRequest` carries `session_id`, immutable plan/step values, zero-based `step_index`, `MemoryContext`, rendered agent context, and immutable step history.
- `ReActAgentService` receives the executor through its constructor and keeps a thin compatibility wrapper during migration.

- [ ] **Step 1: Write the failing denied/failed/timed-out tests**

Build a minimal fake UnitOfWork and a ReAct subclass whose `_call_tool_for_step()` returns a chosen status. Assert:

```python
self.assertEqual(
    [event.type for event in events],
    [
        SessionEventType.step_started,
        SessionEventType.tool_called,
        SessionEventType.step_failed,
    ],
)
self.assertNotIn(SessionEventType.step_completed, event_types)
```

Add a separate approval-required assertion for `step_blocked`, and a deduplicated assertion for `step_completed`.

- [ ] **Step 2: Run the regression test and verify RED**

Run:

```powershell
python -m unittest tests.test_step_failure_semantics -v
```

Expected: denied/failed/timed_out currently end in `step_completed`.

- [ ] **Step 3: Implement the minimal status-aware result**

Add `step_reflected`, `step_failed`, and `step_blocked` event types. Move single-step execution, ToolExecutionContext construction, and step-history formatting into `react_step_executor.py`. The executor emits only `step_started` and `tool_called`; a compatibility method in ReAct appends `step_completed`, `step_failed`, or `step_blocked` with the exact status mapping. Update history formatting so `deduplicated` is a success.

- [ ] **Step 4: Run focused and full tests**

Run:

```powershell
python -m unittest tests.test_step_failure_semantics -v
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/api/app/domain/sessions/entities.py backend/api/app/application/react_step_executor.py backend/api/app/application/react_agent_service.py backend/api/tests/test_step_failure_semantics.py
git commit -m "fix: preserve failed tool outcomes in react execution"
```

### Task 3: Strict Critic Protocol

**Files:**
- Create: `backend/api/app/application/critic_service.py`
- Create: `backend/api/tests/test_critic_service.py`

**Interfaces:**
- Consumes: `RunPlanStep`, `StepObservation`, existing `LLMMessage` and `LLMChatResult`.
- Produces: `CriticModel` Protocol and `CriticService.evaluate(step, observation) -> Reflection`.
- Constructor: `CriticService(model: CriticModel)`; no concrete model is created inside the service.

- [ ] **Step 1: Write failing Critic contract tests**

Use a tiny fake model returning an `LLMChatResult`. Cover:

```python
{"action":"accept","reason":"output matches expected result"}
{"action":"retry","reason":"tool timed out"}
{"action":"replan","reason":"current step cannot satisfy the goal"}
{"action":"fail","reason":"permission denied"}
```

Assert malformed JSON, unknown actions, empty reasons, and `accept` for a failed/denied/timed-out observation raise `AppException`.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest tests.test_critic_service -v
```

Expected: import failure because `critic_service.py` does not exist.

- [ ] **Step 3: Implement strict parsing and evaluation**

The system prompt requests only `action` and `reason`. Parse once with `json.loads`; do not strip Markdown, infer fields, repair output, or catch-and-fallback. Validate the exact action enum and non-empty reason. Reject accepting a non-success observation.

- [ ] **Step 4: Run focused and full tests**

Run:

```powershell
python -m unittest tests.test_critic_service -v
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/api/app/application/critic_service.py backend/api/tests/test_critic_service.py
git commit -m "feat: add strict critic decision protocol"
```

### Task 4: Drive ReAct Through Execute and Reflect States

**Files:**
- Create: `backend/api/app/application/agent_execution_machine.py`
- Create: `backend/api/app/application/agent_summary_service.py`
- Create: `backend/api/app/application/session_file_sync_service.py`
- Modify: `backend/api/app/application/react_agent_service.py`
- Modify: `backend/api/app/application/agent_runner_service.py`
- Create: `backend/api/tests/test_agent_execution_machine.py`
- Modify: `backend/api/tests/test_agent_runner_service.py`

**Interfaces:**
- Consumes: Task 1 router/state, Task 2 `execute_step`, Task 3 `CriticService`.
- Produces: `AgentExecutionMachine.stream(session_id, plan_payload, execution_context) -> AsyncIterator[SessionEvent | tuple[str, str]]`.
- `ReActAgentService.stream_latest_plan()` delegates state progression to this machine.
- `ReActAgentService.execute_latest_plan()` collects SessionEvent objects from the same stream.
- `AgentSummaryService` owns final-evidence rendering and assistant-message persistence.
- `SessionFileSyncService` owns attachment synchronization into the existing sandbox.

- [ ] **Step 1: Write failing orchestration tests**

Inject fake executor, critic, summarizer, and event sink. Assert the successful call order is:

```text
execute(step 0) -> critic(step 0) -> step_completed
execute(step 1) -> critic(step 1) -> step_completed
summarize -> task_done
```

For a denied tool plus Critic `fail`, assert Critic receives the denied observation, the final phase is failed, and no `step_completed` or `task_done` event exists. Add retry coverage proving the same step executes again with incremented attempt. Add replan coverage proving the machine enters `replanning` and invokes the injected replanner or raises an explicit configuration error.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest tests.test_agent_execution_machine -v
```

Expected: import failure because the execution machine does not exist.

- [ ] **Step 3: Implement the pull-state machine**

Each loop iteration dispatches only the node named by `state.phase`. Nodes return a new immutable state plus observable events. Do not add a hidden iteration limit. On `accept`, persist `step_reflected` before `step_completed`; on retry/replan/fail persist the reflection before routing. Unknown phases and missing terminal results raise explicit exceptions.

- [ ] **Step 4: Replace duplicate sync orchestration**

Make `execute_latest_plan()` collect SessionEvent values from `stream_latest_plan()`. Move final-answer helpers to `AgentSummaryService`, move sandbox attachment synchronization to `SessionFileSyncService`, and remove the unused keyword/tool-selection methods from ReAct. Keep direct chat unchanged. Compose `CriticService` with the existing `LLMService` at the AgentRunner/ReAct construction boundary. The resulting `react_agent_service.py` must be at most 300 lines.

- [ ] **Step 5: Run focused and full tests**

Run:

```powershell
python -m unittest tests.test_agent_execution_machine tests.test_agent_runner_service tests.test_agent_runner_direct_chat -v
python -m unittest discover -s tests -v
```

Expected: all tests pass and direct chat behavior is unchanged.

- [ ] **Step 6: Commit**

```powershell
git add backend/api/app/application/agent_execution_machine.py backend/api/app/application/agent_summary_service.py backend/api/app/application/session_file_sync_service.py backend/api/app/application/react_agent_service.py backend/api/app/application/agent_runner_service.py backend/api/tests/test_agent_execution_machine.py backend/api/tests/test_agent_runner_service.py backend/api/tests/test_final_answer_builder.py
git commit -m "feat: orchestrate react with execute reflect states"
```

### Task 5: Documentation and Final Verification

**Files:**
- Modify: `backend/api/ARCHITECTURE.md`
- Modify: `README.md`

**Interfaces:**
- Documents the observable event order and the framework-free state transition table.

- [ ] **Step 1: Update architecture documentation**

Document:

```text
plan_created -> step_started -> tool_called -> step_reflected
step_reflected(accept) -> step_completed
step_reflected(retry) -> same step_started
step_reflected(replan) -> planning adapter
step_reflected(fail) -> step_failed -> task_error
```

State clearly that the current milestone stores observable execution events in SessionEvent and that durable Run Ledger work is a separate next milestone.

- [ ] **Step 2: Run static and automated verification**

Run:

```powershell
python -m compileall -q app tests
python -m unittest discover -s tests -v
git diff --check
```

Expected: compile succeeds, all tests pass, and `git diff --check` is clean.

- [ ] **Step 3: Commit**

```powershell
git add README.md backend/api/ARCHITECTURE.md docs/plans/2026-08-11-custom-agent-state-machine-design.md docs/superpowers/plans/2026-08-11-custom-agent-state-machine.md
git commit -m "docs: describe custom agent execution state machine"
```
