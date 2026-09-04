"""Instrumentation for botocore, and so for boto3 above it: every AWS
API call recorded as one event, categorised by the kind of service it
addresses and named for the service and operation.

This module imports only wrapture. Everything that touches botocore
lives in the sibling client module, which imports only wrapture at top
level (botocore itself is reached through the module the hook is handed
and through a lazy import inside apply), so loading this class when a
config loads never imports botocore ahead of the hook meant to fire on
its import.

boto3 is sugar over botocore: every client method it generates, and
the resource API, paginators and waiters above them, funnel through
one method, so a single binding covers the whole SDK for every AWS
service. The entry point name is the bare target botocore, since that
is where the seam is; a config that says boto3 is really asking for
this.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import client


class BotocoreInstrumentation(wrapture.Instrumentation):
    """Call tracing for the AWS SDK, per-service categorised."""

    description = "Call tracing for the AWS SDK, per-service categorised."

    target = "botocore"
    supports = ">=1.34,<2"
    removable = True

    settings = {
        "leaf": Setting(
            True,
            "record each API call as a terminal node, so the SDK's own"
            " wire work (its urllib3 requests, retries and waiters) and"
            " anything recorded beneath it stay out of the tree",
        ),
    }

    @wrapture.instrumentation_hook("botocore.client")
    def botocore_client(self, name: str, module: Any) -> None:
        """Bind the API call seam once botocore.client exists."""

        client.instrument(module, self)
