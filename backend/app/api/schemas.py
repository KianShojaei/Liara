"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSession(BaseModel):
    title: str = ""
    app: str = ""
    path: str = ""


class SendMessage(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    app: str = ""
    path: str = ""


class ApproveProposal(BaseModel):
    typed_confirmation: str | None = None
    edited_args: dict[str, Any] | None = None  # e.g. env values typed into the card


class RejectProposal(BaseModel):
    reason: str = ""


class WizardEnv(BaseModel):
    values: dict[str, str]


class WizardPlan(BaseModel):
    plan_id: str


class StartInvestigation(BaseModel):
    app: str
    window_minutes: int = 30
    health_path: str = "/"


class RunCodingAgent(BaseModel):
    project_path: str = ""
    demo_patch: bool = False


class ManualStepDone(BaseModel):
    session_id: str
    limitation_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class Remediate(BaseModel):
    option_id: str
    session_id: str = ""
    edited_args: dict[str, Any] | None = None
