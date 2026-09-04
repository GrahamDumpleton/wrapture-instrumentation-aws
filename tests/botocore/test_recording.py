"""What the instrumentation records: one event per AWS API call, the
per-service category, name and contract keys it carries, a failing
call's ClientError recorded with status and code, and what stays out
of capture."""

from __future__ import annotations

import pytest

pytest.importorskip("boto3")
pytest.importorskip("moto")

import boto3
import wrapture
from botocore.exceptions import ClientError
from wrapture import Event, Tape

from tests.botocore.conftest import REGION

SEAM = "botocore.client:BaseClient._make_api_call"


def one(tape: Tape, label: str) -> Event:
    """The single event on the tape with the given label."""

    (event,) = [item for item in tape.all if item.label == label]

    return event


def test_an_s3_call_records_one_external_leaf(aws: None, tape: Tape) -> None:
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="reports")
    s3.put_object(Bucket="reports", Key="q1.csv", Body=b"secret contents")

    event = one(tape, "s3/PutObject")
    assert event.path == SEAM
    assert event.category == "external"
    assert event.exception is None
    assert tape.children_of(event) == []


def test_an_s3_call_carries_the_external_and_resource_keys(
    aws: None, tape: Tape
) -> None:
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="reports")
    s3.put_object(Bucket="reports", Key="q1.csv", Body=b"secret contents")

    event = one(tape, "s3/PutObject")
    data = event.data

    assert data["system"] == "aws"
    assert data["service"] == "s3"
    assert data["operation"] == "PutObject"
    assert data["region"] == REGION
    assert data["host"]
    assert data["port"] == 443
    assert data["url"].startswith("https://")
    assert "?" not in data["url"]
    assert data["bucket"] == "reports"
    assert data["key"] == "q1.csv"
    assert data["status"] == 200
    assert data["request_id"]


def test_the_parameters_reduce_to_a_count_and_the_body_is_nowhere(
    aws: None, tape: Tape
) -> None:
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="reports")
    s3.put_object(Bucket="reports", Key="q1.csv", Body=b"4111111111111111")

    event = one(tape, "s3/PutObject")

    # Bucket, Key and Body: three parameters, recorded as the count,
    # the operation name passing as itself.
    assert event.arguments is not None
    assert event.arguments["operation_name"] == "PutObject"
    assert event.arguments["api_params"] == 3
    assert event.result == "<dict>"

    # The body, nowhere on the event: not in the arguments, not in the
    # data (bucket and key are lifted out by name, the body never).
    assert "4111111111111111" not in repr(event.arguments)
    assert "4111111111111111" not in repr(event.data)


def test_a_dynamodb_call_is_a_datastore_carrying_its_collection(
    aws: None, tape: Tape
) -> None:
    dynamodb = boto3.client("dynamodb")
    dynamodb.create_table(
        TableName="orders",
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    dynamodb.put_item(TableName="orders", Item={"id": {"S": "1"}})

    event = one(tape, "dynamodb/PutItem")
    assert event.category == "datastore"
    assert event.data["service"] == "dynamodb"
    assert event.data["collection"] == "orders"
    assert event.data["status"] == 200
    assert tape.children_of(event) == []


def test_an_sqs_call_is_messaging_carrying_its_destination(
    aws: None, tape: Tape
) -> None:
    sqs = boto3.client("sqs")
    queue = sqs.create_queue(QueueName="jobs")["QueueUrl"]
    sqs.send_message(QueueUrl=queue, MessageBody="run report")

    event = one(tape, "sqs/SendMessage")
    assert event.category == "messaging"
    assert event.data["service"] == "sqs"
    assert event.data["destination"] == "jobs"
    assert event.data["status"] == 200


def test_an_sns_call_is_messaging_carrying_its_topic(aws: None, tape: Tape) -> None:
    sns = boto3.client("sns")
    topic = sns.create_topic(Name="alerts")["TopicArn"]
    sns.publish(TopicArn=topic, Message="disk full")

    event = one(tape, "sns/Publish")
    assert event.category == "messaging"
    assert event.data["destination"] == "alerts"


def test_an_unlisted_service_is_a_plain_external_call(aws: None, tape: Tape) -> None:
    boto3.client("sts").get_caller_identity()

    event = one(tape, "sts/GetCallerIdentity")
    assert event.category == "external"
    assert event.data["service"] == "sts"
    assert "collection" not in event.data
    assert "destination" not in event.data


def test_a_failing_call_records_the_client_error_with_status_and_code(
    aws: None, tape: Tape
) -> None:
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="reports")

    with pytest.raises(ClientError):
        s3.get_object(Bucket="reports", Key="does-not-exist")

    event = one(tape, "s3/GetObject")
    assert isinstance(event.exception, ClientError)
    assert event.data["status"] == 404
    assert event.data["code"] == "NoSuchKey"


def test_a_paginated_list_records_one_event_per_page(aws: None, tape: Tape) -> None:
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="reports")
    for name in ("a", "b", "c"):
        s3.put_object(Bucket="reports", Key=name, Body=b"x")

    pages = list(
        s3.get_paginator("list_objects_v2").paginate(
            Bucket="reports", PaginationConfig={"PageSize": 1}
        )
    )
    assert len(pages) == 3

    calls = [event for event in tape.all if event.label == "s3/ListObjectsV2"]
    assert len(calls) == 3
    assert all(event.data["status"] == 200 for event in calls)


def test_beneath_a_foreign_leaf_the_seam_records_nothing(aws: None, tape: Tape) -> None:
    # Annotation follows recording: silenced beneath another target's
    # leaf, the call records nothing of its own and smears nothing
    # onto the leaf's event.

    @wrapture.observed(leaf=True)
    def vendor() -> None:
        boto3.client("s3").list_buckets()

    vendor()

    (leaf,) = tape.all
    assert tape.children_of(leaf) == []
    assert "service" not in leaf.data
    assert "system" not in leaf.data
