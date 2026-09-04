# Agent guidance for wrapture-instrumentation-aws

## Project

wrapture-instrumentation-aws is packaged instrumentation for the AWS
SDK (boto3 and botocore), applied through wrapture. AWS is the kind of
product the separate-package rule was drawn for: the core
wrapture-instrumentation package covers only targets testable
in-process with no separate backend, and this package carries its own
heavier test dependencies (moto, which pulls in cryptography, PyYAML,
Flask and werkzeug) and its own release cadence. See README.md for
what the project provides and how it is used, and the "Instrumentation
packages" page of the wrapture documentation for the contract every
class here honours.

The package uses a src layout: the code lives in
src/wrapture_instrumentation_aws/, one subpackage per target
(botocore now, an aiobotocore twin later).

Tests live in the tests/ directory, one subdirectory per target. See
TESTING.md for where tests are, how to run them, and the conventions
for adding new ones.

The scratch/ directory is ignored by git. It holds temporary working
files; never reference scratch/ files by name from code or
documentation that will be committed.

## Rules specific to instrumentation

- The module that defines an `Instrumentation` subclass (the target
  subpackage's `__init__.py`) imports wrapture and nothing else.
  Everything that touches the target lives in sibling modules
  imported inside the hook (`from . import client`), themselves
  importing only wrapture at top level and reaching boto3 or botocore
  through the module the hook is handed or a lazy import inside a
  function. wrapture loads the class when the config loads, before the
  application imports anything, and a class whose module imported its
  target would drag the target in ahead of the hook meant to fire on
  its import.

- No target is ever a dependency in pyproject.toml. The only runtime
  dependency is wrapture. boto3, botocore and moto go in the `test`
  dependency group. Never depend on the packages being instrumented.

- The single target here uses a bare subpackage directory
  (`botocore/`), not the core package's `<category>/<target>` role
  directories: one seam fronts several categories (an S3 call is
  external, a DynamoDB call a datastore, an SQS call messaging), so no
  one category names the directory, and the collection is small.
  Entry point names are always the bare target (`botocore`).

- Per-service category, event name and pre-call tags are decided per
  call, not per binding: the single seam on
  `BaseClient._make_api_call` declares `category=`, `label=` and
  `data=` as wrapture resolvers (callables with the `when=`
  signature), which need wrapture 1.0.0a20 or later. The per-service
  table lives in `services.py`; keep the label low-cardinality
  (`service/operation`) and put identifiers in data.

- Every target has its own test suite under `tests/<target>/`,
  runnable alone, and a Justfile recipe to run it against several
  boto3 lines (boto3 drags the matching botocore, whose range the
  class's `supports` is kept honest against).

- Tests validate behaviour with wrapture's own unit testing layer
  (timeline tapes and their queries, `wrapture.instrumentation()` for
  scoping) driving real boto3 clients against moto. moto's in-process
  mode intercepts at botocore's `before-send` event, strictly below
  the `_make_api_call` seam, so the instrumented path is real
  botocore end to end; its threaded server supplies a genuine wire for
  the urllib3 composition and no-propagation tests. Never use
  `unittest.mock`. When a test wants something wrapture's layer cannot
  express, write it the plain way with a comment naming the gap and
  call the gap out in the summary of the work.

- The instrumentation must never bind at or below botocore's HTTP
  send, where in-process moto short-circuits beneath it: the seam
  sits above `before-send` and must stay there.

- Docs for the instrumentation live in the per-target README.md under
  its subpackage, linked from the table in the top README. This
  repository has README.md and CHANGES.md; the module docstrings stay
  contributor-facing implementation commentary.

## Tooling: always use uv

All Python environment and package management in this project is done
with [uv](https://docs.astral.sh/uv/). Never use the Python venv
module, bare pip, or python -m build directly.

- Run commands in the project environment: `uv run <command>`
  (e.g. `uv run pytest`)

- Run a Python interpreter: `uv run python`

- Build sdist and wheel: `uv build`

- Add or remove dependencies (updates pyproject.toml): `uv add <package>`,
  `uv remove <package>`

- Sync the environment from pyproject.toml: `uv sync`

## Common tasks: use the Justfile

The Justfile defines targets for the common development tasks,
wrapping the correct uv invocations. Prefer these targets over
synthesizing the underlying commands yourself; run `just --list` to
see everything.

- `just test` runs the whole test suite on the default Python
  version. Extra arguments pass through to pytest, so a specific file
  or test is `just test tests/botocore/test_recording.py` or
  `just test -k pattern`.

- `just test-target botocore` runs one target's suite.

- `just test-python 3.14t` runs the suite on one nominated Python
  version; `just test-all` runs it on every supported version.

- `just test-botocore 1.34.162` runs the botocore suite against one
  boto3 line; `just test-botocore-all` loops over the list.

- `just test-dev` runs the suite against an editable checkout of
  wrapture in the sibling directory ../wrapture, for iterating against
  unreleased wrapture changes without editing pyproject.toml.

- `just lint` checks with the ruff linter and formatter; `just format`
  reformats and applies auto-fixes.

- `just typecheck` runs mypy.

## Style

- Do not use emdashes in any files in this project. Rephrase with
  commas, parentheses, colons, or separate sentences instead.

- In bulleted lists where items run to multiple lines, put a blank
  line between the bullets: in docstrings, markdown files, and any
  other prose. This is about the raw file being readable, not the
  rendered form, which can look fine either way. Be consistent within
  a list: if one item needs the spacing, space every item in that
  list, never a mix.

- Project code must always use Python type hints. Add them to all
  function and method signatures (parameters and return types), and
  to attributes and variables where the type is not obvious from the
  assignment. When adding or modifying code that lacks type hints,
  add them.

- Use vertical white space liberally inside function and method
  bodies. Write code in paragraphs: group the statements that
  together perform one step, and separate each group from the next
  with a blank line. Natural paragraph boundaries include setup
  versus the main work versus the result, before and after a
  conditional or loop, and around a with or try block. Do not cram a
  body into one contiguous blob, and equally do not put a blank line
  between every single statement; the blank lines should mark where
  one thought ends and the next begins.

- Where it helps the reader, start a paragraph of code with a short
  comment saying what that step does or why it is needed. Prefer one
  comment per logical block over line-by-line commentary, and skip
  the comment entirely when the code already says it plainly.

- Put a blank line between such a block comment and the code below
  it: the comment introduces the paragraph rather than sitting flush
  against its first line.

- Put a blank line between a function or method docstring and the
  first line of code in the body.

- Every function, method or property that is part of the public API
  must have a docstring saying what it does. The exceptions are cases
  that are truly trivial and obvious, such as an accessor property
  named for the attribute it returns, and dunder methods implementing
  standard protocols.

## Git

- The repository follows a main/develop split: develop is the
  working and default branch, main holds releases, and feature
  branches merge to develop.

- Git commit messages must never include a co-authored-by agent
  message or any similar agent attribution trailer.

- An AI agent must never commit changes on its own initiative. Finish
  the piece of work, summarize it, and wait to be told to commit.
  Permission to commit applies only to the work it was given for; it
  does not carry forward to later steps of a multi-step plan, each of
  which needs its own review and its own instruction to commit.
  Uncommitted changes are how the review happens: once work is
  committed it can no longer be reviewed as the pending diff, so
  committing early makes review harder, not easier.

- When merging a feature branch back to develop and pushing to the
  remote, do not treat the work as landed until the CI workflow on
  GitHub has run against the pushed merge and passed. Check the run
  and only once it is green report that the changes are on the remote
  and clean up the feature branch. If CI fails, leave the feature
  branch in place, report the failure, and wait for instructions
  rather than deleting anything.
