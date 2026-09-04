"""The botocore patch: one recording binding on
BaseClient._make_api_call, the choke point every AWS API call passes
through.

Every boto3 client method is generated code that calls this method,
and the resource API, paginators and waiters all sit above it, so one
binding covers the whole SDK for every service. Each call records as
one event: a retry happens inside the call and folds into it, while a
paginator or waiter is several calls and so several events, which is
honest. The binding is an external leaf by default, so the SDK's own
urllib3 wire work stays out of the tree; with leaf off, an
instrumented urllib3 nests beneath it, the same composition the HTTP
clients have.

The category, the label and the pre-call keys all vary per service,
so the binding declares them as resolvers (services.category_of,
label_of and describe), decided per call from the client and the
operation. The decorator adds only what the outcome says, the status,
request id and retry count, and on a ClientError the AWS error code
beside the exception botocore raises; it gates that on owning the
event, so a call silenced beneath another target's leaf annotates
nothing onto that leaf. The pre-call keys need no such gate: a
resolver's data is seeded only when an event is built, so a silenced
call seeds nothing anywhere.

No trace identity is propagated to AWS: v1 injects nothing, and by the
propagation-follows-recording contract a silenced urllib3 beneath the
leaf injects nothing either, so AWS is never handed headers it would
not understand. Trace context into message attributes, and X-Ray
propagation, are later work.
"""

from __future__ import annotations

from typing import Any

import wrapture

from . import common, services


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind BaseClient._make_api_call as a per-service categorised
    call, leaf or not by the leaf setting; register its removal as this
    trigger's cleanup."""

    from botocore.exceptions import ClientError

    settings = instrumentation.settings

    seam = wrapture.binding(
        module.BaseClient,
        "_make_api_call",
        leaf=settings["leaf"],
        category=services.category_of,
        label=services.label_of,
        data=services.describe,
        capture_args=common.captured_argument,
        capture_result="types",
    )

    def record(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # Annotation follows recording: silenced beneath another
        # target's leaf, this call owns no event and must not smear
        # its outcome onto the leaf's.

        owned = bool(wrapture.current_event(binding=seam))

        # botocore raises a ClientError to the application for an error
        # status, so the status is annotated from the response it
        # carries, beside the exception, before it propagates.

        try:
            response = wrapped(*args, **kwargs)
        except ClientError as error:
            if owned:
                wrapture.annotate(**common.outcome(error.response))

                code = common.error_code(error)
                if code is not None:
                    wrapture.annotate(code=code)

            raise

        if owned:
            wrapture.annotate(**common.outcome(response))

        return response

    seam.on_call.decorates(record)
    seam.apply()

    instrumentation.on_cleanup(seam.remove)
