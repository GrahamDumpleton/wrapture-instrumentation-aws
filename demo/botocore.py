"""Drive boto3 against moto with the AWS SDK instrumentation applied.

The instrumentation is resolved by its entry point name, and the
calls go to moto's in-memory backend, so no real AWS and no
credentials beyond dummy ones are needed. The calls cover the shapes
that matter: an S3 put and get (external, with a bucket and key), a
DynamoDB put (a datastore, with a collection), an SQS send (messaging,
with a destination), a paginated list (one event per page), and a
failing get (a ClientError recorded with its status and code). Each
runs beneath an observed function, so the leaves sit in a tree.

Two views of the run always print: the live stream and the tree
reconstructed with timings. With --otel the same events also export
as OpenTelemetry spans to a local OTLP endpoint (http://localhost:4318
unless OTEL_EXPORTER_OTLP_ENDPOINT says otherwise), where each span's
kind and attributes follow the call's category: an S3 call CLIENT with
rpc attributes, a DynamoDB call CLIENT with db attributes, an SQS call
PRODUCER with messaging attributes.
"""

from __future__ import annotations

import argparse
import os
import sys

import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-botocore --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-botocore-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, make the calls against
    moto, print the live stream and the tree, and flush any
    exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.botocore",
        description="Drive boto3 against moto with the instrumentation"
        " applied, printing the live stream and the tree.",
    )
    parser.add_argument(
        "--otel",
        action="store_true",
        help="also export the events as OpenTelemetry spans over OTLP",
    )
    options = parser.parse_args(arguments)

    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

    if options.otel:
        add_otel_sink()

    wrapture.add_sink(wrapture.Printer(stream=sys.stdout))

    print("== live stream ==")

    import boto3
    from botocore.exceptions import ClientError
    from moto import mock_aws

    with (
        mock_aws(),
        wrapture.instrumentation("botocore"),
        wrapture.timeline() as tape,
    ):

        @wrapture.observed
        def exercise() -> None:
            s3 = boto3.client("s3")
            s3.create_bucket(Bucket="reports")
            s3.put_object(Bucket="reports", Key="q1.csv", Body=b"secret contents")
            s3.get_object(Bucket="reports", Key="q1.csv")["Body"].read()

            dynamodb = boto3.client("dynamodb")
            dynamodb.create_table(
                TableName="orders",
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.put_item(TableName="orders", Item={"id": {"S": "1"}})

            sqs = boto3.client("sqs")
            queue = sqs.create_queue(QueueName="jobs")["QueueUrl"]
            sqs.send_message(QueueUrl=queue, MessageBody="run report")

            for name in ("a", "b"):
                s3.put_object(Bucket="reports", Key=name, Body=b"x")
            list(
                s3.get_paginator("list_objects_v2").paginate(
                    Bucket="reports", PaginationConfig={"PageSize": 1}
                )
            )

            try:
                s3.get_object(Bucket="reports", Key="missing")
            except ClientError as error:
                print(f"expected failure: {error.response['Error']['Code']}")

        exercise()

    print()
    print("== tree ==")
    print(tape.tree(times=True))

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print(f"spans flushed to {endpoint} as service wrapture-botocore-demo")


if __name__ == "__main__":
    main()
