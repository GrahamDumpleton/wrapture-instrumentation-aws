"""Applying and removing: the one patched name, and that removal
leaves botocore as it was whatever the setting."""

from __future__ import annotations

import pytest

pytest.importorskip("boto3")

import botocore.client
from wrapture import instrumentation

from wrapture_instrumentation_aws.botocore import BotocoreInstrumentation


def choke_point() -> object:
    """The callable currently at the patched name."""

    return botocore.client.BaseClient._make_api_call


def test_apply_then_remove_leaves_botocore_as_it_was() -> None:
    before = choke_point()

    with instrumentation(BotocoreInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("botocore.client",)
        assert choke_point() is not before

    assert choke_point() is before
    assert not instance.applied


@pytest.mark.parametrize("leaf", [True, False])
def test_every_setting_patches_the_same_name(leaf: bool) -> None:
    # The setting shapes what the binding does, never which name is
    # patched: there is one choke point whatever it says.

    before = choke_point()

    with instrumentation(BotocoreInstrumentation, leaf=leaf):
        assert choke_point() is not before

    assert choke_point() is before


def test_after_removal_a_call_records_nothing(aws: None) -> None:
    import boto3
    from wrapture import timeline

    with instrumentation(BotocoreInstrumentation):
        pass

    with timeline() as tape:
        boto3.client("s3").list_buckets()

    assert tape.all == []
