# wrapture-instrumentation-aws

Instrumentation for the AWS SDK (boto3 and botocore), applied through
[wrapture](https://github.com/GrahamDumpleton/wrapture).

wrapture attaches bindings to arbitrary Python call sites without
modifying the code being observed, and its config layer can switch on
packaged instrumentation for a third-party package by name. This is
the AWS package in that collection: one `wrapture.Instrumentation`
class for the AWS SDK, so tracing every call your application makes to
S3, DynamoDB, SQS and the rest is one config entry and no code.

> **Status: beta, ahead of 1.0.0.** Developed against wrapture's
> beta series, with pre-releases published to
> [PyPI](https://pypi.org/project/wrapture-instrumentation-aws/), and
> until 1.0.0 is final a plain `pip install
> wrapture-instrumentation-aws` picks up the latest pre-release
> automatically, so there is no need to pin a specific version.

## Why a separate package

The core
[wrapture-instrumentation](https://github.com/GrahamDumpleton/wrapture-instrumentation)
package deliberately covers only the standard library and third-party
packages that can be exercised in-process, with no separate backend
product or service needed to test against. AWS is exactly the kind of
product the separate-package rule was drawn for. This package carries
its own heavier test dependencies (moto, which reimplements the AWS
APIs in memory and pulls in cryptography, PyYAML, Flask and werkzeug)
and its own release cadence, so the core package's free-threaded test
matrix stays light. It will grow to hold the AWS SDK's async twin
(aiobotocore) and a messaging trace-propagation layer.

## Installation

```console
$ pip install wrapture-instrumentation-aws
```

Installing it brings wrapture and nothing else. boto3, botocore and
moto are not dependencies: the instrumentation is inert until botocore
is present, and wrapture checks the installed version against the
range the instrumentation supports at apply time.

## Using it

An `[[instrument]]` entry in `wrapture.toml` names the target:

```toml
[[instrument]]
name = "botocore"

[[sink]]
type = "printer"
```

and the runner applies it before the application starts, so the patch
is in place before boto3 is imported:

```console
$ python -m wrapture -m myapp
```

The entry point name is `botocore`, the seam every AWS call passes
through: boto3 is sugar over botocore, so a config that traces
botocore traces boto3. The same config works through
[autowrapt](https://github.com/GrahamDumpleton/autowrapt) injection
(`AUTOWRAPT_BOOTSTRAP=wrapture python myapp.py`); through
[manual setup](https://wrapture.readthedocs.io/en/latest/manual-setup.html),
a few lines in the application's own startup where wrapping the launch
from outside is awkward; and, in a test, through
`wrapture.instrumentation("botocore")` scoping the instrumentation to
a block. The
[ad-hoc tracing guide](https://wrapture.readthedocs.io/en/latest/ad-hoc-tracing.html)
covers the config file itself.

To see what is installed, what it supports in the current
environment, and what settings it takes:

```console
$ python -m wrapture.tools instrumentation --verbose
```

## Provided instrumentation

| Target | Supported versions | Records | Settings |
| ------ | ------------------ | ------- | -------- |
| [`botocore`](https://github.com/GrahamDumpleton/wrapture-instrumentation-aws/blob/develop/src/wrapture_instrumentation_aws/botocore/README.md) | botocore 1.34+ (1.x), and boto3 above it | Every AWS API call as one event at the SDK's single dispatch seam, whichever service or client made it, named `service/operation` (`s3/GetObject`) and categorised per service (S3 external, DynamoDB a datastore, SQS/SNS/Kinesis messaging, Lambda and Step Functions tasks); carrying the system, service, operation, region, endpoint host and port, the resource identifiers (bucket and key, table, queue, topic, stream, function), and from the response the status, request id and any retry count; a failing call's `ClientError` recorded as the exception with its status and AWS error code beside it. Retries fold into the one call; a paginator or waiter is one event per underlying call. The parameters reduce to a count and the response to its type: payloads, items and message bodies are never recorded. | `leaf` |

The entry point name is the config's `name`; the linked per-target
README is the full user documentation: what records, what the events
carry, the setting, and what is deliberately not traced.

## What is not traced

By design, and where it goes:

- No trace identity is propagated to AWS in this version. A silenced
  urllib3 beneath the call injects none either, by wrapture's
  propagation-follows-recording contract, so AWS is never handed
  headers it would not understand. Trace context into SQS, SNS and
  Kinesis message attributes, and X-Ray `X-Amzn-Trace-Id`
  propagation, are planned for later versions.

- The async SDK (aiobotocore, aioboto3) is a separate top-level
  package and will get its own `Instrumentation` class and
  `aiobotocore` entry point in this repository, once the sync target
  is whole.

- s3transfer's multipart uploads fan out to worker threads that do
  not carry the recording context, so those individual calls may not
  nest under the caller.

- Bedrock and other LLM telemetry are out of scope.

## Adding a target

The AWS SDK's one dispatch seam fronts every service, so a single
target covers them all; a future async twin (aiobotocore) would be a
second subpackage and entry point here. The subpackage's `__init__.py`
holds one `wrapture.Instrumentation` subclass and imports only
wrapture; everything that touches botocore lives in sibling modules
(`client.py` for the seam, `services.py` for the per-service table,
`common.py` for the capture policy), imported inside the hook. The
class is registered in `pyproject.toml` under
`[project.entry-points."wrapture.instrumentation"]`, and gets its own
test suite under `tests/<target>/` and a `README.md` linked from the
table above. The
[instrumentation packages](https://wrapture.readthedocs.io/en/latest/instrumentation-packages.html)
page of the wrapture documentation is the full contract; TESTING.md
here covers the tests.

## License

BSD 2-Clause. See
[LICENSE](https://github.com/GrahamDumpleton/wrapture-instrumentation-aws/blob/develop/LICENSE).
