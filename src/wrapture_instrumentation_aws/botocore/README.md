# AWS SDK (botocore) instrumentation

Call tracing for the AWS SDK, [boto3](https://boto3.amazonaws.com/)
and the [botocore](https://github.com/boto/botocore) it is built on.
Entry point name `botocore`, the package it patches (boto3 funnels
every call through it); supports botocore 1.34 and later in the 1.x
line, and any boto3 above it; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "botocore"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("botocore"):
    ...
```

## What you see

One event per AWS API call the application makes, whichever service
or client made it, whether through a client method, the resource API,
a paginator or a waiter:

```
s3/PutObject(operation_name='PutObject', api_params=3)  -> '<dict>'
dynamodb/PutItem(operation_name='PutItem', api_params=2)  -> '<dict>'
sqs/SendMessage(operation_name='SendMessage', api_params=2)  -> '<dict>'
```

Every boto3 client method is generated code that calls one method,
`BaseClient._make_api_call`, and the resource API, paginators and
waiters all sit above it, so a single binding covers the whole SDK
for every AWS service. The event is named `service/operation`, the
low-cardinality form the OpenTelemetry export uses for its span name;
the patched location stays available as `wrapture.path`.

- The event's category is the kind of service the call addresses:
  S3 is an `external` call, DynamoDB a `datastore`, SQS, SNS and
  Kinesis `messaging`, Lambda and Step Functions `task`, and every
  other service a plain `external` call. The one seam decides this
  per call, so the OpenTelemetry export gives an S3 call CLIENT kind
  with `rpc.*` attributes, a DynamoDB call CLIENT with `db.*`, and an
  SQS call PRODUCER with `messaging.*`, all from the one binding.

- Each event carries `system` (`aws`), `service` (`s3`, `dynamodb`),
  `operation` (`GetObject`, `PutItem`), `region`, and the endpoint
  `host`, `port` and `url`. The service's resource is named too:
  `bucket` and `key` for S3, `collection` for a DynamoDB table (the
  database contract's key, exported as `db.collection.name`), and
  `destination` for an SQS queue, an SNS topic, a Kinesis stream, a
  Lambda function or a Step Functions state machine (exported as
  `messaging.destination.name`).

- From the response the event carries `status`
  (`ResponseMetadata.HTTPStatusCode`), `request_id` (the id AWS
  support correlates by), and `retries` when the call retried. A
  retry happens inside the call and folds into the one event; a
  paginator or waiter is several calls and so several events, which
  is honest.

- The event is a terminal node of the tree, a leaf: it covers
  everything the call did, and the SDK's own wire work (its urllib3
  requests, connection handling and retries) records nothing beneath
  it. With `leaf = false` an instrumented urllib3 nests beneath it,
  the wire phases of each attempt shown.

- botocore raises a `ClientError` to the application for an error
  status, so a failing call (getting a nonexistent object, say)
  records that exception, with the `status` and the AWS error `code`
  (`NoSuchKey`, `ResourceNotFoundException`) annotated beside it from
  the response the error carries.

## Sensitive data

The capture policy is deliberate about what an AWS call carries.
`api_params` is never recorded wholesale: it holds payloads, items,
message bodies and occasionally credentials, so it reduces to a count
of how many parameters were passed, and the response reduces to its
type. The resource identifiers named above are the only values lifted
out of the parameters, by known name.

One of those, the S3 `key`, is an object path that can embed user
data, and it is recorded. It is the same shape as a recorded URL
path, and every major agent records it, but if your object keys carry
anything you would not want on a trace, mask it with a sink-side
policy or leave S3 out with a service filter (a later setting). A
`StreamingBody` response (an object's bytes) is consumed by the
application after the call returns, outside the event, so its contents
are never captured.

No trace identity is propagated to AWS. This version injects nothing,
and a silenced urllib3 beneath the leaf injects nothing either, so AWS
is never handed `traceparent` headers it would not understand.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `leaf` | `true` | Whether each API call is a terminal node. Off, the SDK's own urllib3 requests record beneath it as children (the wire phases of each attempt, when the `urllib3` target is applied as well), for debugging the SDK itself. |

```toml
[[instrument]]
name = "botocore"
leaf = false
```

## With the urllib3 instrumentation

botocore does its HTTP through real urllib3, so with the core
package's `urllib3` target applied as well, an AWS call still records
once: the botocore leaf silences the urllib3 request beneath it. Turn
the `botocore` leaf off to see the wire work nested beneath each call.

## How it patches

For the implementation detail see the module docstrings of
[client.py](client.py) (the seam), [services.py](services.py) (the
per-service category, name and identifier table) and
[common.py](common.py) (the capture policy).
