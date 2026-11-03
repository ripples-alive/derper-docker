import copy
import datetime as dt
import unittest
from unittest.mock import patch

from scripts import workflow_health as health

NOW = dt.datetime(2026, 1, 10, 12, tzinfo=dt.UTC)
REPO = {"id": 42, "full_name": "example/relay", "default_branch": "main"}
ASSIGNEE = "maintainer"


def run(number=10, conclusion="success", **overrides):
    result = {
        "id": number * 100,
        "run_number": number,
        "run_attempt": 1,
        "head_branch": "main",
        "head_repository": {"id": 42},
        "event": "schedule",
        "status": "completed",
        "conclusion": conclusion,
        "created_at": NOW.isoformat(),
    }
    result.update(overrides)
    return result


class FakeAPI:
    def __init__(self):
        self.issues = []
        self.runs = {w.file: [run(event=w.events[0])] for w in health.WORKFLOWS}
        self.states = {w.file: "active" for w in health.WORKFLOWS}
        self.writes = []
        self.drop_assignment = False

    def pages(self, path, key=None):
        if path.startswith("/issues?"):
            return iter(copy.deepcopy(self.issues))
        return iter(copy.deepcopy(self.runs[path.split("/")[3]]))

    def request(self, method, path, payload=None):
        if method == "GET":
            if path.startswith("/actions/workflows/"):
                return {"state": self.states[path.split("/")[-1]]}
            return copy.deepcopy(next(i for i in self.issues if i["number"] == int(path.split("/")[-1])))
        self.writes.append((method, path, copy.deepcopy(payload)))
        if method == "POST":
            issue = {"number": len(self.issues) + 1, "state": "open", "user": {"login": health.BOT}}
            self.issues.insert(0, issue)
        else:
            issue = next(i for i in self.issues if i["number"] == int(path.split("/")[-1]))
        issue.update(copy.deepcopy(payload))
        issue["assignees"] = [] if self.drop_assignment else [{"login": login} for login in payload["assignees"]]
        return copy.deepcopy(issue)


class WorkflowHealthTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()

    def reconcile(self, **kwargs):
        return health.reconcile(self.api, REPO, ASSIGNEE, NOW, **kwargs)

    def fail_updater(self, number=10):
        self.api.runs["update-tailscale.yml"] = [run(number, "failure")]

    def test_healthy_repository_does_not_create_issues(self):
        self.assertEqual(self.reconcile(), [])

    def test_failure_assigns_issue_and_duplicate_event_is_noop(self):
        self.fail_updater()
        self.reconcile()
        self.assertEqual(len(self.api.issues), 1)
        issue = self.api.issues[0]
        self.assertEqual(issue["assignees"], [{"login": ASSIGNEE}])
        self.assertIn("/actions/runs/1000", issue["body"])
        self.assertEqual(self.reconcile(), [])
        self.assertEqual(len(self.api.writes), 1)

    def test_repeated_failure_updates_same_issue_without_comment(self):
        self.fail_updater()
        self.reconcile()
        self.fail_updater(11)
        self.reconcile()
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual([w[:2] for w in self.api.writes], [("POST", "/issues"), ("PATCH", "/issues/1")])
        self.assertIn("/actions/runs/1100", self.api.issues[0]["body"])

    def test_recovery_closes_and_recurrence_reopens_same_issue(self):
        self.fail_updater()
        self.reconcile()
        self.api.runs["update-tailscale.yml"] = [run(11)]
        self.reconcile()
        self.assertEqual(self.api.issues[0]["state"], "closed")
        self.assertIn("Recovered", self.api.issues[0]["body"])
        self.assertEqual(self.reconcile(), [])
        self.fail_updater(12)
        self.reconcile()
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(self.api.issues[0]["state"], "open")

    def test_inflight_and_cancelled_runs_do_not_clear_failure(self):
        self.fail_updater()
        self.reconcile()
        for status, conclusion in [("in_progress", None), ("queued", None), ("completed", "cancelled")]:
            with self.subTest(status=status, conclusion=conclusion):
                self.api.runs["update-tailscale.yml"] = [run(11, conclusion, status=status)]
                self.assertEqual(self.reconcile(), [])
                self.assertEqual(self.api.issues[0]["state"], "open")

    def test_all_failure_conclusions_alert(self):
        for conclusion in health.FAILURES | {"neutral", "skipped"}:
            with self.subTest(conclusion=conclusion):
                self.api = FakeAPI()
                self.api.runs["update-tailscale.yml"] = [run(conclusion=conclusion)]
                self.assertEqual(len(self.reconcile()), 1)

    def test_daily_workflow_stale_or_disabled_alerts_despite_last_success(self):
        old = (NOW - dt.timedelta(hours=49)).isoformat()
        self.api.runs["update-tailscale.yml"] = [run(created_at=old)]
        self.api.states["keepalive.yml"] = "disabled_inactivity"
        self.reconcile()
        self.assertEqual(len(self.api.issues), 2)
        self.assertTrue(any("48 hours" in issue["body"] for issue in self.api.issues))
        self.assertTrue(any("disabled" in issue["body"] for issue in self.api.issues))

    def test_stale_publication_is_not_a_daily_workflow_failure(self):
        self.api.runs["docker-image.yml"] = [run(event="push", created_at=(NOW - dt.timedelta(days=90)).isoformat())]
        self.assertEqual(self.reconcile(), [])

    def test_pr_fork_and_other_branch_cannot_close_existing_failure(self):
        self.fail_updater()
        self.reconcile()
        untrusted = [run(13, event="pull_request"), run(12, head_repository={"id": 99}), run(11, head_branch="feature")]
        self.api.runs["update-tailscale.yml"] = untrusted + [run(10, "failure")]
        self.assertEqual(self.reconcile(), [])
        self.assertEqual(self.api.issues[0]["state"], "open")

    def test_manual_image_validation_cannot_close_publication_failure(self):
        self.api.runs["docker-image.yml"] = [run(10, "failure", event="push")]
        self.reconcile()
        self.api.runs["docker-image.yml"].insert(0, run(11, event="workflow_dispatch"))
        self.assertEqual(self.reconcile(), [])
        self.assertEqual(self.api.issues[0]["state"], "open")

    def test_only_matching_bot_owned_issues_are_modified(self):
        self.api.issues = [{"number": 100, "user": {"login": "someone"}, "body": health.marker(health.WORKFLOWS[0])}]
        self.fail_updater()
        self.reconcile()
        self.assertEqual(self.api.writes[0][0], "POST")
        self.assertNotIn("state", self.api.issues[-1])

    def test_another_workflow_success_does_not_close_failure(self):
        self.fail_updater()
        self.reconcile()
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(self.api.issues[0]["state"], "open")

    def test_dry_run_reads_live_decision_without_writes(self):
        self.fail_updater()
        self.assertEqual(self.reconcile(dry_run=True)[0]["method"], "POST")
        self.assertEqual(self.api.writes, [])

    def test_readback_rejects_silently_dropped_assignment(self):
        self.fail_updater()
        self.api.drop_assignment = True
        with self.assertRaisesRegex(RuntimeError, "readback"):
            self.reconcile()

    def test_api_failure_does_not_close_existing_issue(self):
        self.fail_updater()
        self.reconcile()
        with patch.object(self.api, "request", side_effect=RuntimeError("API unavailable")):
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                self.reconcile()
        self.assertEqual(len(self.api.writes), 1)
        self.assertEqual(self.api.issues[0]["state"], "open")

    def test_missing_daily_run_alerts(self):
        self.api.runs["update-tailscale.yml"] = []
        self.reconcile()
        self.assertIn("No eligible", self.api.issues[0]["body"])

    def test_invalid_assignee_fails_before_writes(self):
        with self.assertRaises(ValueError):
            health.reconcile(self.api, REPO, "@bad user", NOW)
        self.assertEqual(self.api.writes, [])


if __name__ == "__main__":
    unittest.main()
