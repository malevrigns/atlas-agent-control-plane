"""内存版 Redis 替身，模拟 Stream + consumer group 的关键语义。

比「返回全部消息」的简易替身更严格：这里真实维护 pending 列表，
``xreadgroup`` 只投递未投递过的消息，``xack`` 之后不再重发。契约测试
里「同一条消息不会被领取两次」这类断言必须靠这个行为才有意义。
"""

import time


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict] = {}
        # entries: message_id -> payload
        self.entries: dict[str, dict] = {}
        # 已投递未确认：message_id -> 投递时间
        self.pending: dict[str, float] = {}
        self.delivered: set[str] = set()
        self.group_start_id: str | None = None
        self.acked: list[str] = []
        self._sequence = 0

    # ===================== Hash =====================
    async def hset(self, key: str, mapping: dict) -> None:
        self.hashes.setdefault(key, {}).update(mapping)

    async def hgetall(self, key: str) -> dict:
        return dict(self.hashes.get(key, {}))

    # ===================== Stream =====================
    async def xadd(self, stream_name: str, payload: dict) -> str:
        self._sequence += 1
        message_id = f"{self._sequence}-0"
        self.entries[message_id] = dict(payload)
        return message_id

    async def xgroup_create(self, stream_name: str, group: str, id: str, mkstream: bool) -> None:
        self.group_start_id = id

    async def xreadgroup(self, group: str, consumer: str, streams: dict, block: int, count: int):
        fresh = [
            (message_id, payload)
            for message_id, payload in sorted(self.entries.items())
            if message_id not in self.delivered
        ][:count]
        now = time.time()
        for message_id, _ in fresh:
            self.delivered.add(message_id)
            self.pending[message_id] = now
        return [(next(iter(streams)), fresh)]

    async def xautoclaim(self, stream_name, group, consumer, min_idle_time, start_id, count):
        cutoff = time.time() - min_idle_time / 1000
        claimed = [
            (message_id, self.entries[message_id])
            for message_id, delivered_at in sorted(self.pending.items())
            if delivered_at <= cutoff
        ][:count]
        for message_id, _ in claimed:
            self.pending[message_id] = time.time()
        return ["0-0", claimed, []]

    async def xack(self, stream_name: str, group: str, message_id: str) -> None:
        self.acked.append(message_id)
        self.pending.pop(message_id, None)

    async def xinfo_groups(self, stream_name: str):
        return [{"name": "atlas-agent-runners", "pending": len(self.pending)}]

    async def aclose(self) -> None:
        return None
