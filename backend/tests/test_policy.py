import tempfile
from pathlib import Path

import pytest

from app.policy.engine import PolicyConfig, PolicyEngine
from app.policy.proposals import STATUS_PENDING, STATUS_VERIFIED, Impact, ProposalService
from app.store.db import Store


def make_store() -> Store:
    return Store(Path(tempfile.mkdtemp()) / "t.sqlite")


def test_tiers_and_guards():
    engine = PolicyEngine(PolicyConfig(app_allowlist={"a"}, cost_guard_hourly=100))
    assert engine.decide("get_app", {"app": "a"}).mode == "auto"
    assert engine.decide("recheck_dns", {"zone": "x"}).mode == "notice"
    assert engine.decide("restart_app", {"app": "a"}).mode == "approval"
    assert engine.decide("restart_app", {"app": "b"}).mode == "blocked"
    assert engine.decide("delete_app", {"app": "a"}).mode == "blocked"
    assert engine.decide("resize_app", {"app": "a"}, cost_delta_hourly=500).mode == "blocked"
    assert (
        PolicyEngine(PolicyConfig(enable_guarded=True))
        .decide("delete_app", {"app": "a"})
        .requires_typed_confirmation
    )


def test_approval_tokens_are_bound_and_single_use():
    engine = PolicyEngine(PolicyConfig())
    token, digest = engine.issue_approval_token("prp_1")
    assert engine.verify_approval_token("prp_1", token, digest)
    assert not engine.verify_approval_token("prp_2", token, digest)
    assert not engine.verify_approval_token("prp_1", "bad.token", digest)


@pytest.mark.asyncio
async def test_proposal_lifecycle_with_verification():
    store = make_store()
    service = ProposalService(
        store, PolicyEngine(PolicyConfig(), secret=store.get_or_create_secret())
    )
    calls = []

    async def executor(args):
        calls.append(args)
        return {"restarted": args["app"]}

    async def verifier(args, result):
        return {"ok": True, "steps": [{"name": "http", "ok": True, "detail": "200"}]}

    service.register("restart_app", executor, verifier)
    session = store.create_session(title="t")
    proposal, decision, _ = service.propose(
        session["id"], "restart_app", {"app": "a"}, title="r", summary="s", impact=Impact()
    )
    assert decision.mode == "approval" and proposal["status"] == STATUS_PENDING

    with pytest.raises(PermissionError):
        await service.execute(proposal["id"])  # not approved yet
    token = service.human_token(proposal["id"])
    assert token and service.human_token(proposal["id"]) is None  # single use
    service.approve(proposal["id"], token)
    with pytest.raises(PermissionError):
        service.approve(proposal["id"], token)  # replay rejected
    final = await service.execute(proposal["id"])
    assert final["status"] == STATUS_VERIFIED and calls == [{"app": "a"}]
    actions = [row["action"] for row in store.audit_log()]
    assert {"propose", "approve", "execute", "verify"} <= set(actions)


@pytest.mark.asyncio
async def test_model_cannot_run_t2_automatically():
    store = make_store()
    service = ProposalService(store, PolicyEngine(PolicyConfig()))

    async def executor(args):
        return {}

    service.register("restart_app", executor)
    with pytest.raises(PermissionError):
        await service.run_auto("s", "restart_app", {"app": "a"})
