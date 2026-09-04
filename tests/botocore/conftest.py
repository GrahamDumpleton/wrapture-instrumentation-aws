"""Fixtures for the botocore suite: dummy AWS credentials and a region,
moto's in-memory backend, and a tape hearing the instrumentation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# boto3 (which drags botocore) and moto are the suite's own test
# dependencies; a build without them (a free threaded one where moto's
# wheels are missing) skips rather than errors.
pytest.importorskip("boto3")
pytest.importorskip("moto")

from moto import mock_aws
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation_aws.botocore import BotocoreInstrumentation

REGION = "us-east-1"


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Dummy credentials and a region in the environment, and moto's
    in-memory backend active for the test.

    moto answers each request from an in-memory backend at botocore's
    before-send event, strictly below the _make_api_call seam, so
    everything the instrumentation touches is real botocore.
    """

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    with mock_aws():
        yield


@pytest.fixture
def tape(aws: None) -> Iterator[Tape]:
    """A tape hearing the botocore instrumentation, moto's backend
    active beneath it."""

    with instrumentation(BotocoreInstrumentation), timeline() as recorded:
        yield recorded
