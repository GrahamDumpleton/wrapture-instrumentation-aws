"""With the core package's urllib3 target applied as well: botocore
does its HTTP through real urllib3, so by default the botocore leaf
silences it, and switching that leaf off exposes it beneath. Driven
over a real wire (moto's threaded server) so urllib3 actually runs,
where in-process moto would short-circuit beneath the seam.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("boto3")
pytest.importorskip("moto")
# The urllib3 target lives in the core wrapture-instrumentation
# package; without it there is nothing to compose against.
pytest.importorskip("wrapture_instrumentation.external.urllib3")

import boto3
from moto.server import DomainDispatcherApplication, create_backend_app
from werkzeug.serving import BaseWSGIServer, make_server
from wrapture import Event, Tape, instrumentation, timeline
from wrapture_instrumentation.external.urllib3 import Urllib3Instrumentation

from tests.botocore.conftest import REGION
from wrapture_instrumentation_aws.botocore import BotocoreInstrumentation


@dataclass
class MotoServer:
    """A real moto server on a loopback port, recording the headers of
    each request it receives so a test can see the wire."""

    url: str
    requests: list[dict[str, str]] = field(default_factory=list)


class _HeaderRecorder:
    """WSGI middleware wrapping moto's app, keeping each request's
    headers for the test to read back."""

    def __init__(self, app: Any, sink: list[dict[str, str]]) -> None:
        self._app = app
        self._sink = sink

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Any:
        headers = {
            key[5:].replace("_", "-").lower(): value
            for key, value in environ.items()
            if key.startswith("HTTP_")
        }
        self._sink.append(headers)

        return self._app(environ, start_response)


@pytest.fixture
def moto_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[MotoServer]:
    """A threaded moto server with dummy credentials and a region in
    the environment, boto3 pointed at it via endpoint_url."""

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    record = MotoServer(url="")
    app = _HeaderRecorder(
        DomainDispatcherApplication(create_backend_app), record.requests
    )

    httpd: BaseWSGIServer = make_server("127.0.0.1", 0, app)
    record.url = f"http://127.0.0.1:{httpd.server_address[1]}"

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield record
    finally:
        # werkzeug's serve_forever calls server_close() itself, in
        # its finally on the serving thread, so closing here as well
        # would race it (seen as EBADF on the free-threaded builds).
        # Joining the thread is what guarantees the close has run.

        httpd.shutdown()
        thread.join()


def urllib3_events(tape: Tape) -> list[Event]:
    return [event for event in tape.all if "urllib3" in (event.path or "")]


def workload(server: MotoServer) -> None:
    s3 = boto3.client("s3", endpoint_url=server.url)
    s3.create_bucket(Bucket="reports")
    s3.put_object(Bucket="reports", Key="q1.csv", Body=b"contents")


def test_the_botocore_leaf_silences_urllib3_beneath_it(moto_server: MotoServer) -> None:
    with (
        instrumentation(BotocoreInstrumentation),
        instrumentation(Urllib3Instrumentation),
        timeline() as tape,
    ):
        workload(moto_server)

    # Each API call is one leaf, urllib3's own work beneath it out.

    put = next(event for event in tape.all if event.label == "s3/PutObject")
    assert put.data["status"] == 200
    assert urllib3_events(tape) == []


def test_the_leaf_off_exposes_urllib3_beneath_the_call(moto_server: MotoServer) -> None:
    with (
        instrumentation(BotocoreInstrumentation, leaf=False),
        instrumentation(Urllib3Instrumentation),
        timeline() as tape,
    ):
        workload(moto_server)

    # With the botocore leaf off, urllib3's request records beneath
    # the API call, itself a leaf that then hides http.client below.

    put = next(event for event in tape.all if event.label == "s3/PutObject")
    children = tape.children_of(put)
    assert children
    assert all("urllib3" in (child.path or "") for child in children)


def test_the_default_leaf_sends_no_trace_identity_to_aws(
    moto_server: MotoServer,
) -> None:
    # v1 propagates nothing at the botocore level, and by the
    # propagation-follows-recording contract a urllib3 silenced
    # beneath the leaf injects nothing either, so AWS is handed no
    # traceparent it would not understand.

    with (
        instrumentation(BotocoreInstrumentation),
        instrumentation(Urllib3Instrumentation),
        timeline(),
    ):
        workload(moto_server)

    assert moto_server.requests
    assert all("traceparent" not in headers for headers in moto_server.requests)


def test_raw_urllib3_use_beside_a_call_still_records(moto_server: MotoServer) -> None:
    import urllib3

    with (
        instrumentation(BotocoreInstrumentation),
        instrumentation(Urllib3Instrumentation),
        timeline() as tape,
    ):
        workload(moto_server)

        with urllib3.PoolManager() as manager:
            manager.request("GET", f"{moto_server.url}/")

    # The direct urllib3 call is nobody's child, so it records its own
    # leaf even while the botocore one silences its internal use.

    roots = [event for event in tape.all if tape.parent_of(event) is None]
    assert any("urllib3" in (event.path or "") for event in roots)
