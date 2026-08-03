from dataclasses import dataclass


@dataclass(slots=True)
class SecurityCheck:
    """一条面向安全边界的检查项。"""

    key: str
    name: str
    category: str
    severity: str
    risk: str
    recommendation: str
    verify_command: str
