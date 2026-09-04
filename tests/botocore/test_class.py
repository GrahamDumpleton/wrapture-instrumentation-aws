"""The class as wrapture reads it: its data, its settings, and the
installed botocore satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

pytest.importorskip("boto3")

# boto3 is imported for its side: it imports botocore.client, on whose
# import the class's trigger fires, so the applying test below works
# with this file run on its own.
import boto3  # noqa: F401
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation_aws.botocore import BotocoreInstrumentation


def test_class_data() -> None:
    assert BotocoreInstrumentation.target == "botocore"
    assert BotocoreInstrumentation.removable is True
    assert BotocoreInstrumentation.requires == ()
    assert BotocoreInstrumentation.supports == ">=1.34,<2"

    assert set(BotocoreInstrumentation.settings) == {"leaf"}
    assert BotocoreInstrumentation.settings["leaf"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    assert (BotocoreInstrumentation.__doc__ or "").splitlines()[0] == (
        "Call tracing for the AWS SDK, per-service categorised."
    )


def test_constructing_without_settings_works() -> None:
    instance = BotocoreInstrumentation()

    assert instance.settings == {"leaf": True}
    assert instance.applied == ()
    assert instance.pending == ("botocore.client",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="propagate"):
        BotocoreInstrumentation(propagate=True)


def test_a_setting_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        BotocoreInstrumentation(leaf="no")


def test_the_installed_botocore_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(BotocoreInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("botocore")
            assert applied.applied == ("botocore.client",)
            assert applied.pending == ()
