"""Read-only Projects v2 collection. Never log response payloads or credentials."""

import json
import os
import time
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import click
import urllib3
from github import GithubException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.db_models import (
    FlowBoard,
    FlowCollectionRun,
    FlowSnapshot,
)
from app.projects.flow_metrics.locking import lock_collection
from app.shared.config.app_config import app_config
from app.shared.database import db
from app.shared.services.github_app_auth_service import get_github_app_auth_headers

BOARD_ID = "ministryofjustice/152"
ESTIMATION_FIELD_ID = "PVTF_lADOACGfts4BHZqSzg_lEkY"
MAX_ITEMS = 10000
ITEM_PAGE_SIZE = 20
VALUE_FIELDS = """
__typename
... on ProjectV2ItemFieldSingleSelectValue { name optionId field { ... on ProjectV2FieldCommon { id name } } }
... on ProjectV2ItemFieldIterationValue { title iterationId startDate duration field { ... on ProjectV2FieldCommon { id name } } }
... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { id name } } }
... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2FieldCommon { id name } } }
... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { id name } } }
"""
PAGE_INFO = "pageInfo { hasNextPage endCursor }"
ISSUE_REFERENCE = "number repository { nameWithOwner }"
METADATA_CONNECTIONS = {
    "assignees": "login",
    "labels": "name",
    "blockedBy": ISSUE_REFERENCE,
    "blocking": ISSUE_REFERENCE,
    "relatesTo": ISSUE_REFERENCE,
    "reviewRequests": "requestedReviewer { ... on User { login } ... on Team { slug organization { login } } }",
    "reviews": "author { login }",
}
COMMON_METADATA = f"""
assignees(first:100) {{ nodes {{ login }} {PAGE_INFO} }}
labels(first:100) {{ nodes {{ name }} {PAGE_INFO} }}
milestone {{ title }}
"""
ISSUE_METADATA = (
    COMMON_METADATA
    + f"""
parent {{ {ISSUE_REFERENCE} }}
subIssuesSummary {{ total completed percentCompleted }}
blockedBy(first:100) {{ nodes {{ {ISSUE_REFERENCE} }} {PAGE_INFO} }}
blocking(first:100) {{ nodes {{ {ISSUE_REFERENCE} }} {PAGE_INFO} }}
relatesTo(first:100) {{ nodes {{ {ISSUE_REFERENCE} }} {PAGE_INFO} }}
"""
)
PR_METADATA = (
    COMMON_METADATA
    + f"""
reviewRequests(first:100) {{ nodes {{ {METADATA_CONNECTIONS["reviewRequests"]} }} {PAGE_INFO} }}
reviews(first:100) {{ nodes {{ author {{ login }} }} {PAGE_INFO} }}
"""
)
ITEM_QUERY = f"""
query($cursor:String) {{
  organization(login:"ministryofjustice") {{ projectV2(number:152) {{
    id
    items(first:{ITEM_PAGE_SIZE},after:$cursor) {{
      totalCount
      nodes {{
        id isArchived
        content {{
          __typename
          ... on Issue {{ id number title createdAt state issueType {{ name }} repository {{ nameWithOwner }} {ISSUE_METADATA} }}
          ... on PullRequest {{ id number title createdAt state repository {{ nameWithOwner }} {PR_METADATA} }}
          ... on DraftIssue {{ id title createdAt }}
        }}
        fieldValues(first:100) {{ nodes {{ {VALUE_FIELDS} }} {PAGE_INFO} }}
      }}
      {PAGE_INFO}
    }}
  }} }}
}}
"""
FIELD_QUERY = f"""
query($cursor:String) {{
  organization(login:"ministryofjustice") {{ projectV2(number:152) {{
    fields(first:100,after:$cursor) {{
      nodes {{
        ... on ProjectV2FieldCommon {{ id name dataType }}
        ... on ProjectV2SingleSelectField {{ options {{ id name }} }}
        ... on ProjectV2IterationField {{ configuration {{
          iterations {{ id title startDate duration }}
          completedIterations {{ id title startDate duration }}
        }} }}
      }}
      {PAGE_INFO}
    }}
  }} }}
}}
"""


class CollectionError(Exception):
    """A safe code, never a GitHub response containing private item data."""


def collect_metadata(client, content):
    kind = content["__typename"]
    if kind not in {"Issue", "PullRequest"}:
        return
    for name, selection in METADATA_CONNECTIONS.items():
        if name not in content:
            continue
        first = content[name]

        def fetch(cursor, name=name, selection=selection, first=first):
            if cursor is None:
                return first
            query = f"query($id:ID!,$cursor:String){{node(id:$id){{... on {kind} {{{name}(first:100,after:$cursor){{nodes{{{selection}}} {PAGE_INFO}}}}}}}}}"
            return client.query(query, id=content["id"], cursor=cursor)["node"][name]

        values = []
        for page in pages(fetch):
            for node in page["nodes"]:
                if node is None:
                    raise CollectionError("github_metadata_inaccessible")
                if name == "reviewRequests":
                    reviewer = node.get("requestedReviewer") or {}
                    value = reviewer.get("login") or (
                        f"{reviewer['organization']['login']}/{reviewer['slug']}"
                        if reviewer.get("slug")
                        else None
                    )
                elif name == "reviews":
                    value = (node.get("author") or {}).get("login")
                elif name in {"blockedBy", "blocking", "relatesTo"}:
                    value = f"{node['repository']['nameWithOwner']}#{node['number']}"
                else:
                    value = node.get("login") or node.get("name")
                if value:
                    values.append(value)
        content[name] = sorted(set(values))


class ProjectClient:
    def __init__(self):
        config = app_config.github.app
        if config.client_id and config.private_key and config.installation_id:
            try:
                self.headers = get_github_app_auth_headers(
                    config.client_id, config.private_key, config.installation_id
                )
            except (GithubException, ValueError):
                raise CollectionError("github_app_authentication_failed") from None
        elif os.getenv("FLOW_METRICS_LOCAL_TOKEN") and not app_config.auth_enabled:
            self.headers = {
                "Authorization": f"Bearer {os.environ['FLOW_METRICS_LOCAL_TOKEN']}"
            }
        else:
            raise CollectionError("github_credentials_missing")
        self.http = urllib3.PoolManager()

    def query(self, query, **variables):
        for attempt in range(3):
            try:
                response = self.http.request(
                    "POST",
                    "https://api.github.com/graphql",
                    headers={
                        **self.headers,
                        "Content-Type": "application/json",
                        "User-Agent": "MoJ-Flow-Metrics",
                    },
                    body=json.dumps({"query": query, "variables": variables}),
                    timeout=urllib3.Timeout(connect=10, read=60),
                    retries=False,
                )
            except urllib3.exceptions.HTTPError:
                if attempt == 2:
                    raise CollectionError("github_connection_failed") from None
                time.sleep(2**attempt)
                continue
            if response.status >= 500 and attempt < 2:
                time.sleep(2**attempt)
                continue
            if response.status != 200:
                raise CollectionError(f"github_http_{response.status}")
            try:
                data = json.loads(response.data)
            except (ValueError, UnicodeError):
                raise CollectionError("github_invalid_response") from None
            if data.get("errors") or not data.get("data"):
                raise CollectionError("github_query_incomplete")
            return data["data"]
        raise CollectionError("github_unavailable")


def pages(fetch, max_pages=101):
    cursor = None
    seen = set()
    while True:
        page = fetch(cursor)
        if not isinstance(page, dict) or not isinstance(page.get("nodes"), list):
            raise CollectionError("github_page_incomplete")
        yield page
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
        if not cursor or cursor in seen or len(seen) >= max_pages - 1:
            raise CollectionError("github_pagination_invalid")
        seen.add(cursor)


def collect_payload(client, field_mapping=None):
    fields = []
    for page in pages(
        lambda cursor: client.query(FIELD_QUERY, cursor=cursor)["organization"][
            "projectV2"
        ]["fields"]
    ):
        for field in page["nodes"]:
            if not field or not field.get("id"):
                raise CollectionError("github_field_inaccessible")
            fields.append(field)
    allowed_names = {
        "Status",
        "Team",
        "Sprint",
        "Type",
        "Planned",
        "Objective",
        "Points",
        "Priority",
        "Refined",
    }
    allowed_ids = {field["id"] for field in fields if field["name"] in allowed_names}
    estimation = next((field for field in fields if field["id"] == ESTIMATION_FIELD_ID), None)
    if estimation:
        if estimation.get("dataType") != "NUMBER":
            raise CollectionError("estimation_field_type_changed")
        allowed_ids.add(ESTIMATION_FIELD_ID)
    allowed_ids.update(value for value in (field_mapping or {}).values() if value)
    if not allowed_ids.issubset({field["id"] for field in fields}):
        raise CollectionError("configured_field_missing")
    items = []
    item_ids = set()
    project_id = None
    total = None

    def fetch(cursor):
        nonlocal project_id, total
        project = client.query(ITEM_QUERY, cursor=cursor)["organization"]["projectV2"]
        if not project:
            raise CollectionError("github_board_inaccessible")
        if project_id and project["id"] != project_id:
            raise CollectionError("github_board_changed")
        project_id = project["id"]
        count = project["items"]["totalCount"]
        if total is not None and total != count:
            raise CollectionError("github_board_changed_during_collection")
        total = count
        if type(count) is not int or count < 0:
            raise CollectionError("github_item_count_invalid")
        if count > MAX_ITEMS:
            raise CollectionError("board_item_limit_exceeded")
        return project["items"]

    for page in pages(fetch, max_pages=(MAX_ITEMS + ITEM_PAGE_SIZE - 1) // ITEM_PAGE_SIZE):
        for item in page["nodes"]:
            if (
                not item
                or not item.get("content")
                or item["content"].get("__typename") == "RedactedProjectV2Item"
            ):
                raise CollectionError("github_item_inaccessible")
            if item["id"] in item_ids:
                raise CollectionError("github_item_count_mismatch")
            if len(items) >= MAX_ITEMS:
                raise CollectionError("board_item_limit_exceeded")
            item_ids.add(item["id"])
            values = []
            collect_metadata(client, item["content"])
            first = item["fieldValues"]

            def more(cursor, first=first, item_id=item["id"]):
                if cursor is None:
                    return first
                query = f"query($id:ID!,$cursor:String){{node(id:$id){{... on ProjectV2Item {{fieldValues(first:100,after:$cursor){{nodes{{{VALUE_FIELDS}}} {PAGE_INFO}}}}}}}}}"
                return client.query(query, id=item_id, cursor=cursor)["node"][
                    "fieldValues"
                ]

            for value_page in pages(more):
                for value in value_page["nodes"]:
                    if not value:
                        raise CollectionError("github_field_value_inaccessible")
                    if value.get("field") and value["field"]["id"] in allowed_ids:
                        values.append(value)
            items.append(
                {
                    "id": item["id"],
                    "archived": item["isArchived"],
                    "content": item["content"],
                    "fields": values,
                }
            )
    if len(items) != total:
        raise CollectionError("github_item_count_mismatch")
    return {
        "project_id": project_id,
        "fields": [field for field in fields if field["id"] in allowed_ids],
        "items": items,
        "metadataVersion": 1,
    }


def collect(client=None):
    board = db.session.get(FlowBoard, BOARD_ID)
    if board is None:
        raise CollectionError("flow_database_not_initialised")
    run = FlowCollectionRun(
        id=str(uuid4()),
        board_id=BOARD_ID,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.session.add(run)
    db.session.commit()
    try:
        lock_collection()
        board = db.session.execute(
            select(FlowBoard).where(FlowBoard.id == BOARD_ID)
            .execution_options(populate_existing=True)
        ).scalar_one()
        mapping = deepcopy(board.field_mapping)
        payload = collect_payload(client or ProjectClient(), mapping)
        captured_at = datetime.now(UTC)
        board = db.session.execute(
            select(FlowBoard).where(FlowBoard.id == BOARD_ID)
            .with_for_update().execution_options(populate_existing=True)
        ).scalar_one()
        if board.field_mapping != mapping:
            raise CollectionError("field_mapping_changed_during_collection")
        return publish(run, payload, captured_at)
    except (KeyError, TypeError, ValueError, CollectionError, SQLAlchemyError) as error:
        db.session.rollback()
        run.status = "failed"
        run.error_code = (
            str(error) if isinstance(error, CollectionError)
            else "snapshot_publication_failed" if isinstance(error, SQLAlchemyError)
            else "github_response_schema_invalid"
        )
        run.completed_at = datetime.now(UTC)
        db.session.commit()
        raise CollectionError(run.error_code) from None


def publish(run, payload, captured_at):
    from app.projects.flow_metrics.archive import snapshot_document
    from app.projects.flow_metrics.datasets import retain_evidence

    # Serialise publication; incomplete collections never replace a snapshot.
    board = db.session.execute(
        select(FlowBoard).where(FlowBoard.id == BOARD_ID).with_for_update()
    ).scalar_one()
    names = {
        "status": "Status",
        "team": "Team",
        "sprint": "Sprint",
        "type": "Type",
        "planned": "Planned",
        "objective": "Objective",
        "points": "Points",
        "priority": "Priority",
        "refined": "Refined",
    }
    board.field_mapping = {
        key: (board.field_mapping or {}).get(key)
        or next(
            (field["id"] for field in payload["fields"] if field["name"] == name),
            None,
        )
        for key, name in names.items()
    }
    estimation = next(
        (field for field in payload["fields"] if field["id"] == ESTIMATION_FIELD_ID), None,
    )
    if estimation:
        if estimation.get("dataType") != "NUMBER":
            raise CollectionError("estimation_field_type_changed")
        # Estimation is a unitless number, separate from fictional story points.
        board.field_mapping = {**board.field_mapping, "estimate": ESTIMATION_FIELD_ID}
        payload["estimateBinding"] = {
            "fieldId": ESTIMATION_FIELD_ID, "name": estimation["name"],
            "dataType": "NUMBER", "unit": "number",
        }
    payload["mapping"] = board.field_mapping
    snapshot = db.session.execute(
        select(FlowSnapshot).where(
            FlowSnapshot.board_id == BOARD_ID, FlowSnapshot.captured_date == captured_at.date()
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = FlowSnapshot(
            id=str(uuid4()), board_id=BOARD_ID, captured_date=captured_at.date()
        )
        db.session.add(snapshot)
    else:
        retain_evidence(snapshot_document(snapshot))
    snapshot.payload = payload
    snapshot.captured_at = captured_at
    retain_evidence(snapshot_document(snapshot))
    run.status = "complete"
    run.completed_at = datetime.now(UTC)
    db.session.commit()
    return len(payload["items"])


@click.command("collect")
def collect_command():
    """Collect project 152 with read-only credentials; publish only complete data."""
    try:
        count = collect()
    except (CollectionError, SQLAlchemyError) as error:
        if isinstance(error, SQLAlchemyError):
            db.session.rollback()
            raise click.ClickException(
                "Flow Metrics database operation failed; no payload logged."
            ) from None
        raise click.ClickException(str(error)) from None
    click.echo(
        f"Complete: {count} board items observed. No item details written to logs."
    )
