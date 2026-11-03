#!/usr/bin/env python3
"""Reconcile release workflow failures into assigned, deduplicated GitHub issues."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Workflow:
    file: str
    name: str
    events: tuple[str, ...]
    max_age_hours: int | None = None


WORKFLOWS = (
    Workflow("update-tailscale.yml", "Tailscale stable release", ("schedule", "workflow_dispatch"), 48),
    Workflow("docker-image.yml", "Docker image publication", ("push",)),
    Workflow("keepalive.yml", "Repository keepalive", ("schedule", "workflow_dispatch"), 48),
)
FAILURES = {"failure", "timed_out", "action_required", "startup_failure", "stale"}
BOT = "github-actions[bot]"


class GitHub:
    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid repository")
        self.base = f"https://api.github.com/repos/{repository}"
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "workflow-health",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Never include response bodies, tokens, or workflow logs in errors.
            raise RuntimeError(f"GitHub {method} {path.split('?')[0]} returned HTTP {error.code}") from None

    def pages(self, path: str, key: str | None = None):
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            result = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            items = result[key] if key else result
            yield from items
            if len(items) < 100:
                return
        raise RuntimeError("GitHub pagination limit reached")


def latest_run(api, repository: dict, workflow: Workflow) -> dict | None:
    branch = urllib.parse.quote(repository["default_branch"], safe="")
    path = f"/actions/workflows/{workflow.file}/runs?branch={branch}"
    for run in api.pages(path, "workflow_runs"):
        if (
            run.get("head_branch") == repository["default_branch"]
            and (run.get("head_repository") or {}).get("id") == repository["id"]
            and run.get("event") in workflow.events
        ):
            return run
    return None


def problem(workflow: Workflow, metadata: dict, run: dict | None, now: dt.datetime) -> str | None:
    if metadata.get("state") != "active":
        return "The workflow is disabled."
    if run is None:
        return "No eligible default-branch workflow run was found."
    started = dt.datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    if workflow.max_age_hours and now - started > dt.timedelta(hours=workflow.max_age_hours):
        return f"The daily workflow has not started a new run in over {workflow.max_age_hours} hours."
    if run.get("conclusion") in FAILURES:
        return f"The latest run ended with `{run['conclusion']}`."
    if run.get("status") == "completed" and run.get("conclusion") not in {"success", "cancelled"}:
        return "The latest run did not complete successfully."
    return None


def marker(workflow: Workflow) -> str:
    return f"<!-- workflow-health:{workflow.file} -->"


def managed_issue(issues: list[dict], workflow: Workflow) -> dict | None:
    for issue in issues:
        if (
            "pull_request" not in issue
            and issue.get("user", {}).get("login") == BOT
            and marker(workflow) in (issue.get("body") or "").splitlines()
        ):
            return issue
    return None


def reconcile(api, repository: dict, assignee: str, now: dt.datetime, dry_run: bool = False) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", assignee):
        raise ValueError("ALERT_ASSIGNEE must be one GitHub login")
    issues = list(api.pages("/issues?state=all&sort=created&direction=desc"))
    actions = []
    for workflow in WORKFLOWS:
        metadata = api.request("GET", f"/actions/workflows/{workflow.file}")
        run = latest_run(api, repository, workflow)
        issue = managed_issue(issues, workflow)
        reason = problem(workflow, metadata, run, now)
        # In-flight/cancelled runs are neither a successful recovery nor a failure.
        if not reason and (not run or run.get("conclusion") != "success"):
            continue
        if not reason and (not issue or issue["state"] == "closed"):
            continue
        status = "Action required" if reason else "Recovered"
        body = f"{marker(workflow)}\n\n{status}: **{workflow.name}**\n\n"
        body += (reason or "The latest eligible run succeeded.") + "\n\n"
        if run:
            url = f"https://github.com/{repository['full_name']}/actions/runs/{int(run['id'])}"
            body += f"[Run {run['run_number']}, attempt {run.get('run_attempt', 1)}]({url})\n\n"
        body += (
            "This issue is maintained automatically. Repeated failures update the same issue; "
            "a successful run closes it. See the linked run for job details.\n"
        )
        payload = {
            "title": f"[CI alert] {workflow.name}",
            "body": body,
            "state": "open" if reason else "closed",
            "assignees": [assignee],
        }
        if not reason:
            payload["state_reason"] = "completed"
        elif issue and issue["state"] == "closed":
            payload["state_reason"] = "reopened"
        if issue:
            if all(issue.get(key) == payload[key] for key in ("title", "body", "state")) and [
                person["login"] for person in issue.get("assignees", [])
            ] == [assignee]:
                continue
            method, path = "PATCH", f"/issues/{issue['number']}"
        else:
            method, path = "POST", "/issues"
            payload.pop("state")
        actions.append({"workflow": workflow.file, "method": method, "path": path, "status": status})
        if not dry_run:
            result = api.request(method, path, payload)
            # Verify the persisted state and assignee, including silently rejected assignments.
            saved = api.request("GET", f"/issues/{result['number']}")
            if (
                saved.get("state") != ("open" if reason else "closed")
                or saved.get("body") != body
                or assignee not in [person["login"] for person in saved.get("assignees", [])]
            ):
                raise RuntimeError("Issue readback did not match the intended notification")
    return actions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Read live state without writing issues")
    args = parser.parse_args()
    api = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
    repository = api.request("GET", "")
    result = reconcile(api, repository, os.environ["ALERT_ASSIGNEE"], dt.datetime.now(dt.UTC), args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
