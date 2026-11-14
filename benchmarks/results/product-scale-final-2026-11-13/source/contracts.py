"""Small versioned data contracts used by the evidence foundation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    started_at: datetime
    coverage: tuple[str, ...] = ()


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    step_index: int = Field(ge=0)
    kind: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
