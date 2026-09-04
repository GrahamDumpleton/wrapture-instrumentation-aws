# Testing

## Where the tests are

Tests live in the [tests/](tests/) directory at the top of the
repository, separate from the package code in
src/wrapture_instrumentation_aws/. Test files are named `test_*.py`
and are discovered by pytest, configured via the
`[tool.pytest.ini_options]` section of [pyproject.toml](pyproject.toml).

The directory has two levels:

- Package-level tests directly under tests/: the version, the rule
  that importing the package or loading any registered class never
  imports a target, and the listing tool reporting every entry
  cleanly.

- One subdirectory per target, `tests/<target>/` (`tests/botocore/`),
  holding that instrumentation's suite: settings validation, applying
  and removing the class directly, the whole path through
  `wrapture.instrumentation()` with a timeline recording what the
  bindings observe, resolving the entry point by name, a check that
  the installed botocore satisfies the class's `supports` range, and
  the composition tests over a real wire.

Shared helpers live in [tests/conftest.py](tests/conftest.py).

## Testing with moto

The suite drives real boto3 clients against
[moto](https://docs.getmoto.org/), which reimplements the AWS APIs in
memory. Two modes are used, and the split maps onto what the suite
needs:

- In-process mode (`moto.mock_aws` as a context manager) registers a
  `before-send` handler on botocore's event system and answers each
  request from the in-memory backend, no socket. Everything above
  `before-send`, `_make_api_call` included, is real botocore
  executing normally, so the instrumented path is exercised with full
  fidelity. This is the workhorse: the `aws` fixture opens `mock_aws()`
  with dummy credentials and a region in the environment, and the
  tests drive real clients and assert the tape.

- Server mode (`ThreadedMotoServer` from `moto.server`, on a thread,
  no docker) is a real HTTP server speaking the AWS protocols on
  localhost, with boto3 pointed at it via `endpoint_url`. It supplies
  a genuine wire for the composition tests with the core package's
  urllib3 target, and for asserting what headers the request carried
  on the wire.

Because the seam sits strictly above moto's in-process interception,
the tests are faithful; the corollary is that this instrumentation
must never bind at or below botocore's HTTP send, where in-process
moto would short-circuit beneath it.

moto needs cryptography, which has no free threaded wheel for 3.13 or
3.15 yet, so those two builds are left out of the version matrix
rather than run with nothing installed. The suites also guard their
imports with `pytest.importorskip`, so a build where moto or the core
package is absent skips rather than errors.

## Running the tests

All tooling in this project goes through
[uv](https://docs.astral.sh/uv/), which manages the project
environment and installs the package, its development dependencies
(including pytest) and the target packages the tests need.

The simplest way to run the test suite is via the Justfile target:

```console
just test
```

Extra arguments are passed through to pytest, for example:

```console
just test -v
just test tests/botocore/test_recording.py
just test -k redirect
```

One target's suite alone:

```console
just test-target botocore
```

Equivalently, run pytest directly with uv:

```console
uv run pytest
```

## Watching what the tests record

The suites assert on tapes rather than printing anything, but the
recorded events can be watched live for visual verification. Setting
WRAPTURE_PRINTER in the environment installs a process-wide
wrapture.Printer sink for the session, streaming one line to stderr as
each operation begins and a closing line with its outcome and timing;
pytest captures stderr, so add -s to see it:

```console
WRAPTURE_PRINTER=1 just test tests/botocore -s
```

For a purpose-built run rather than the tests' traffic, the demo
module under demo/ applies the instrumentation, drives boto3 against
moto, and prints both the live stream and the reconstructed tree with
timings:

```console
just demo-botocore
```

With --otel the same events also export as OpenTelemetry spans over
OTLP (to http://localhost:4318, or wherever
OTEL_EXPORTER_OTLP_ENDPOINT points), for verifying the spans in a
local backend such as Jaeger; the Justfile target overlays the
wrapture[otel] dependencies for the run:

```console
just demo-botocore --otel
```

## Testing across Python versions

The project supports Python 3.12 through 3.15, and the free threaded
build of 3.14. The supported list is defined at the top of the
[Justfile](Justfile); the free threaded builds of 3.13 and 3.15 are
excluded until moto's dependency wheels exist for them. The default
version used by plain `just test` is pinned in
[.python-version](.python-version).

```console
just test-all
just test-python 3.14t
```

uv downloads any Python version it does not already have, and each
version gets its own environment (.venv-VERSION) so the default .venv
is left untouched.

## Testing across target versions

The `test` dependency group installs boto3 (and so botocore) at
whatever version the lock resolves. The instrumentation's `supports`
range is kept honest by running the suite against other boto3 lines,
overlaid on the project environment for that run; boto3 pins botocore
to its matching minor, so overlaying boto3 is how a botocore line is
tested. Each line has a place in `boto3_versions` in the Justfile, run
one at a time by `just test-botocore 1.34.162` or all by
`just test-botocore-all`, and the CI workflow runs the same matrix. A
test in the suite asserts the installed botocore satisfies `supports`,
so a matrix entry outside the range fails loudly rather than passing
vacuously.

## Testing against unreleased wrapture

The package depends on a released wrapture. To run the tests against a
checkout of wrapture in the sibling directory ../wrapture, without
editing pyproject.toml:

```console
just test-dev
```

which overlays that checkout as an editable install for the run. This
is the way to exercise the package against unreleased wrapture
changes, such as a new resolver capability the seam relies on.

## Writing tests

- Put new test files in tests/ (package level) or tests/<target>/
  (for one instrumentation) and name them `test_*.py`.

- Import the package under test as `wrapture_instrumentation_aws`, and
  the instrumentation classes from their subpackages. The project is
  installed into the uv-managed environment, so no path manipulation
  is needed.

- Guard the target imports with `pytest.importorskip` at the top of
  the module (`boto3 = pytest.importorskip("boto3")`), so a build
  without moto or boto3 skips the suite rather than erroring.

- Validate behaviour with wrapture's own unit testing layer:
  `wrapture.timeline()` to record what the instrumentation's bindings
  observe and the tape's tree and queries to assert on it, and
  `wrapture.instrumentation()` to scope an application of a class to a
  block, driving real boto3 clients against moto. Do not use
  `unittest.mock`. If something cannot be expressed that way, write it
  plainly with a comment naming the gap, and say so when summarising
  the work.

- Tests should not depend on anything in the scratch/ directory,
  which is not part of the repository.
