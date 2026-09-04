"""The entry point: resolving the instrumentation by its bare name,
and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

import pytest

pytest.importorskip("boto3")
pytest.importorskip("moto")

import boto3
from moto import mock_aws
from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from wrapture_instrumentation_aws import __version__
from wrapture_instrumentation_aws.botocore import BotocoreInstrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("botocore") as record:
        (instance,) = record.instrumentations

        assert type(instance) is BotocoreInstrumentation
        assert instance.name == "botocore"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Call tracing for the AWS SDK, per-service categorised."
        )


def test_a_config_entry_applies_and_reverts(aws: None) -> None:
    applied = Config(instrument=[InstrumentEntry("botocore")]).apply()
    try:
        report = applied.report()
        assert "botocore" in report
        assert f"target botocore {metadata.version('botocore')}" in report
        assert "applied botocore.client" in report

        with timeline() as tape:
            boto3.client("s3").list_buckets()

        assert [event.path for event in tape.all] == [
            "botocore.client:BaseClient._make_api_call"
        ]
    finally:
        applied.revert()

    with mock_aws(), timeline() as tape:
        boto3.client("s3").list_buckets()

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"botocore  ({DISTRIBUTION} {__version__})" in output
    assert "  Call tracing for the AWS SDK, per-service categorised." in output
    assert (
        f"  target: botocore {metadata.version('botocore')},"
        " supported (>=1.34,<2)" in output
    )
    assert "  modules: botocore.client" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    leaf = true " in output
    assert (
        "record each API call as a terminal node, so the SDK's own wire work" in output
    )


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "botocore"\nenabled = false' in output
    assert "# leaf = true" in output
