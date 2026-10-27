import asyncio

import pytest

from app.core.base_guard import BaseGuard
from app.core.context import RequestContext
from app.core.errors import PolicyError
from app.core.pipeline import GuardPipeline
from app.core.policy import GuardSpec, build_pipeline, load_policy
from app.core.types import Action, Detection, FailMode, Stage


class Boom(BaseGuard):
    name = "boom"

    async def scan(self, text, ctx):
        raise RuntimeError("model server down")


class Slow(BaseGuard):
    name = "slow"

    async def scan(self, text, ctx):
        await asyncio.sleep(1)
        return Detection(triggered=False)


class Flagger(BaseGuard):
    name = "flagger"

    async def scan(self, text, ctx):
        return Detection(triggered="bad" in text, score=1.0, reason="contains 'bad'")


def run(pipeline, text="hello"):
    return asyncio.run(pipeline.run(text, RequestContext("t")))


def test_fail_closed_blocks():
    out = run(GuardPipeline([Boom(fail_mode=FailMode.CLOSED)], Stage.INPUT))
    assert out.blocked and out.blocked_by.error


def test_fail_open_allows():
    out = run(GuardPipeline([Boom(fail_mode=FailMode.OPEN)], Stage.INPUT))
    assert not out.blocked and out.results[0].error


def test_timeout_respects_fail_mode():
    out = run(GuardPipeline([Slow(fail_mode=FailMode.OPEN, timeout_s=0.05)], Stage.INPUT))
    assert not out.blocked and out.results[0].error == "timeout"


def test_flag_lets_request_through_but_records_it():
    out = run(GuardPipeline([Flagger(action=Action.FLAG)], Stage.INPUT), "bad input")
    assert not out.blocked and out.triggered == ["flagger"]


def test_block_action_blocks():
    out = run(GuardPipeline([Flagger(action=Action.BLOCK)], Stage.INPUT), "bad input")
    assert out.blocked and out.blocked_by.guard == "flagger"


def test_invalid_guard_config_rejected():
    with pytest.raises(PolicyError):
        Flagger(action=Action.REDACT)  # cannot redact
    with pytest.raises(PolicyError):
        Flagger(not_a_param=1)
    with pytest.raises(PolicyError):
        build_pipeline([GuardSpec(type="does_not_exist")], Stage.INPUT)


def test_policy_file_errors(tmp_path):
    with pytest.raises(PolicyError):
        load_policy(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("input: [: not yaml")
    with pytest.raises(PolicyError):
        load_policy(bad)
