from dataclasses import dataclass


@dataclass(slots=True)
class ObservabilityCheck:
    """一条面向排查的诊断项。"""

    key: str
    name: str
    category: str
    description: str
    command: str
    expected: str
