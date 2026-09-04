# Supported Python versions. moto (through cryptography) has no free
# threaded wheel for 3.13 or 3.15 yet, so those two builds are left
# out: the whole suite depends on moto, and a build where it will not
# install would pass with nothing run. Add 3.13t and 3.15t back when
# the wheels exist.
python_versions := "3.12 3.13 3.14 3.14t 3.15"

# One representative boto3 release per line to run the suite against;
# boto3 drags the matching botocore, whose version the instrumentation's
# `supports` range is kept honest by. The lock's own latest is covered
# by the plain `test` runs, so it is not repeated here.
boto3_versions := "1.34.162 1.38.46"

# List available targets.
default:
    @just --list

# Run the test suite on the default Python version; extra args go to pytest.
test *ARGS:
    uv run pytest {{ARGS}}

# Run one target's test suite, e.g. `just test-target botocore`.
test-target TARGET *ARGS:
    uv run pytest tests/{{TARGET}} {{ARGS}}

# Extra arguments are passed through to pytest. Each version gets its own
# environment so the default .venv is untouched, and only the test
# dependency group is installed: dev tools such as mypy do not build on
# the free threaded versions and are not needed to run tests.
# Run the test suite on one nominated version, e.g. `just test-python 3.14t`.
test-python VERSION *ARGS:
    UV_PROJECT_ENVIRONMENT=.venv-{{VERSION}} uv run --python {{VERSION}} --no-default-groups --group test pytest {{ARGS}}

# Run the test suite on every supported Python version.
test-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{python_versions}}; do
        echo "=== Python ${version} ==="
        just test-python "${version}" {{ARGS}}
    done

# The botocore suite against one boto3 version, overlaid on the project
# environment for that run, so the lock's version stays the default and
# older lines need no environment of their own. boto3 pins botocore to
# its matching minor, so overlaying boto3 is how a botocore line is
# tested.
# Run the botocore suite against one boto3 version, e.g. `just test-botocore 1.34.162`.
test-botocore VERSION *ARGS:
    uv run --with "boto3=={{VERSION}}" pytest tests/botocore {{ARGS}}

# Run the botocore suite against every version in boto3_versions.
test-botocore-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{boto3_versions}}; do
        echo "=== boto3 ${version} ==="
        just test-botocore "${version}" {{ARGS}}
    done

# Drive boto3 against moto with the instrumentation applied, an S3
# put/get, a DynamoDB put/get, an SQS send and a failing call, then the
# same over a real wire (ThreadedMotoServer) composed with the urllib3
# target; the live event stream, then the reconstructed tree. The
# wrapture[otel] overlay carries the optional OpenTelemetry
# dependencies, so `just demo-botocore --otel` also exports the events
# as spans to a local OTLP endpoint (localhost:4318 unless
# OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
demo-botocore *ARGS:
    uv run --with "wrapture[otel]" python -m demo.botocore {{ARGS}}

# The package depends on a released wrapture. This overlays a checkout
# of wrapture from the sibling directory as an editable install for the
# run, for iterating against unreleased wrapture changes without
# touching pyproject.toml.
# Run the test suite against the wrapture checkout in ../wrapture.
test-dev *ARGS:
    uv run --with-editable ../wrapture pytest {{ARGS}}

# Check code with the ruff linter and formatter.
lint:
    uv run ruff check src tests demo
    uv run ruff format --check src tests demo

# Reformat code and fix lint issues that are auto-fixable.
format:
    uv run ruff format src tests demo
    uv run ruff check --fix src tests demo

# Type check the project with mypy.
typecheck:
    uv run mypy

# Build the source distribution and wheel into dist/.
build:
    uv build

# Remove temporary files: caches, virtual environments and build artifacts.
clean:
    rm -rf .venv .venv-*
    rm -rf build dist src/*.egg-info *.egg-info
    rm -rf .pytest_cache .mypy_cache .ruff_cache
    find . -type d -name __pycache__ -not -path "./scratch/*" -exec rm -rf {} +
