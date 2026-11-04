"""Local structural and factual validation; no claim of server-side strict mode."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_file: str = Field(min_length=1, max_length=200)
    status: Literal["normal", "diagnosed", "uncertain"]
    fault: Literal["normal", "bearing_wear", "misalignment", "overload", "cavitation"]
    health_index: float = Field(ge=0, le=100, allow_inf_nan=False)
    summary: str = Field(min_length=1, max_length=1500)
    recommendations: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(min_length=1, max_length=8)


def validate_grounding(report: DiagnosticReport, facts: dict) -> None:
    for field in ("source_file", "status", "fault", "health_index"):
        if getattr(report, field) != facts[field]:
            raise ValueError(f"Report contradicts tool facts: {field}")
