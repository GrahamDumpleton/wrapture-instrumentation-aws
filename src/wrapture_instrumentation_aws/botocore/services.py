"""The per-service table: what category an AWS service's calls are,
what the event is named, and which parameters name the resource it
touches.

One seam (BaseClient._make_api_call) fronts every service, so the
category, the label and the pre-call tags are all decided per call
from the client the method was invoked on and the operation and
parameters it was handed. The three functions below are the resolvers
the binding declares, each with wrapture's per-operation signature
(instance, args, kwargs): instance is the botocore client, args is
(operation_name, api_params). They read the client's own metadata and
the operation's parameters, never the payload.

The table is complete for the services worth subdividing and silent
for the rest, which record as plain external calls. It is keyed by
the lowercase service name botocore reports (s3, dynamodb, sqs), and
maps each to the category its calls are and the contract keys lifted
from api_params by name: collection for a datastore, destination for
a messaging or task target, exported by wrapture's OpenTelemetry
export as db.collection.name and messaging.destination.name. S3 is an
external call (the agents do not treat object storage as a database),
carrying its bucket and key as plain data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}

# The category each service's calls are. A service absent here records
# as "external", the plain client call.

CATEGORIES: dict[str, str] = {
    "dynamodb": "datastore",
    "sqs": "messaging",
    "sns": "messaging",
    "kinesis": "messaging",
    "lambda": "task",
    "stepfunctions": "task",
}

# The resource identifiers to lift from api_params, per service: a
# contract key, the parameter names that may carry it (the first
# present wins), and an optional reducer to the low-cardinality tail.

Reducer = Callable[[Any], str]

IDENTIFIERS: dict[str, tuple[tuple[str, tuple[str, ...], Reducer | None], ...]] = {
    "dynamodb": (("collection", ("TableName",), None),),
    "sqs": (("destination", ("QueueUrl", "QueueName"), None),),
    "sns": (("destination", ("TopicArn", "TargetArn"), None),),
    "kinesis": (("destination", ("StreamName",), None),),
    "lambda": (("destination", ("FunctionName",), None),),
    "stepfunctions": (("destination", ("stateMachineArn",), None),),
    "s3": (("bucket", ("Bucket",), None), ("key", ("Key",), None)),
}


def _tail(value: Any) -> str:
    """The last segment of a slash or colon separated identifier: a
    queue URL, a topic or state machine ARN reduced to its name."""

    text = str(value).rstrip("/")

    return text.rsplit("/", 1)[-1].rsplit(":", 1)[-1]


# The reducers above are None where the parameter is already the bare
# name; a queue URL, a topic ARN and a state machine ARN reduce to
# their tail. Assigned here to keep the table readable.

for _service, _entries in IDENTIFIERS.items():
    IDENTIFIERS[_service] = tuple(
        (key, names, _tail if key == "destination" else reduce)
        for key, names, reduce in _entries
    )


def service_of(instance: Any) -> str:
    """The lowercase service name the client addresses (s3, dynamodb,
    sqs), from its own service model."""

    return str(instance.meta.service_model.service_name)


def operation_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """The operation name as AWS spells it (GetObject, PutItem), the
    first positional argument of the call."""

    if args:
        return str(args[0])

    return str(kwargs.get("operation_name"))


def params_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    """The operation parameters, the second positional argument."""

    if len(args) > 1:
        params = args[1]
    else:
        params = kwargs.get("api_params")

    return params if isinstance(params, dict) else {}


def category_of(instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """The category this call is: the table's word for its service, or
    external for a service the table does not subdivide."""

    return CATEGORIES.get(service_of(instance), "external")


def label_of(instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """The event's name, service/operation (s3/GetObject), the
    low-cardinality form the OpenTelemetry export and the printer both
    show, with the resource identifiers left to data."""

    return f"{service_of(instance)}/{operation_of(args, kwargs)}"


def describe(
    instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    """The keys known before the call: the system and service identity,
    the operation, the region and endpoint location, and the resource
    identifiers the table names for this service."""

    meta = instance.meta
    service = service_of(instance)

    data: dict[str, Any] = {
        "system": "aws",
        "service": service,
        "operation": operation_of(args, kwargs),
    }

    region = getattr(meta, "region_name", None)
    if region:
        data["region"] = region

    endpoint = getattr(meta, "endpoint_url", None)
    if endpoint:
        parts = urlsplit(endpoint)

        if parts.hostname:
            data["host"] = parts.hostname

            port = parts.port or DEFAULT_PORTS.get(parts.scheme)
            if port is not None:
                data["port"] = port

        # The endpoint without any query, the external contract's url
        # key; AWS endpoints carry none, but strip defensively.

        data["url"] = urlunsplit(
            (parts.scheme, parts.netloc.rpartition("@")[2], parts.path, "", "")
        )

    params = params_of(args, kwargs)
    for key, names, reduce in IDENTIFIERS.get(service, ()):
        for name in names:
            if name in params:
                value = params[name]
                data[key] = reduce(value) if reduce is not None else value
                break

    return data
