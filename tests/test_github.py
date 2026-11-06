"""The bot's GitHub adapter and the repository-host interface (proof-of-fix#104, #82 B4), against a fake GitHub on the
loopback: issues without pull requests, labels, comments, pagination, merge state, retries and rate limits, and the
config choosing a host per repository. No network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # fake_github, when run as tests.test_github

from bot import forge  # noqa: E402
from bot.github import GitHubError, GitHubRepo  # noqa: E402
from fake_github import FakeGitHub  # noqa: E402

REPO = "demo/sample"


class TestGitHubAdapter(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub(page_size=2).__enter__()
        self.addCleanup(self.gh.__exit__)
        self.sleeps = []
        self.repo = GitHubRepo(REPO, token=self.gh.token, api=self.gh.url, sleep=self.sleeps.append,
                               now=lambda: 1_000.0)
        self.i1 = self.gh.add_issue(REPO, "bug one", "Reporter wallet: 0x" + "11" * 20, labels=["bounty"])
        self.i2 = self.gh.add_issue(REPO, "bug two", "text", labels=["bug"])
        self.i3 = self.gh.add_issue(REPO, "bug three", "text", labels=["bounty"])
        self.pr = self.gh.add_pull(REPO, "fix", "Bounty: 1", "c" * 40)

    def test_issues_leave_out_pull_requests_and_follow_pages(self):
        numbers = [i["number"] for i in self.repo.issues()]
        self.assertEqual(numbers, [self.i1, self.i2, self.i3])  # 3 issues over 2 pages; the PR left out
        self.assertEqual([i["number"] for i in self.repo.issues(label="bounty")], [self.i1, self.i3])
        self.assertEqual(self.repo.issue(self.i1)["labels"], ["bounty"])

    def test_comments_round_trip(self):
        self.repo.comment(self.i1, "linked")
        self.assertEqual([c["body"] for c in self.repo.comments(self.i1)], ["linked"])

    def test_pull_head_and_merge_state(self):
        p = self.repo.pull(self.pr)
        self.assertEqual((p["head_sha"], p["merged"]), ("c" * 40, False))
        self.gh.merge(REPO, self.pr)
        self.assertTrue(self.repo.merged(self.pr))

    def test_pulls_list_with_head_base_and_merge_state(self):
        second = self.gh.add_pull(REPO, "another fix", "Bounty: 1", "d" * 40, base_sha="e" * 40)
        self.gh.merge(REPO, second)
        pulls = {p["number"]: p for p in self.repo.pulls()}  # a judge finds its submission's pull request here
        self.assertEqual(set(pulls), {self.pr, second})
        self.assertEqual((pulls[second]["head_sha"], pulls[second]["base_sha"], pulls[second]["merged"]),
                         ("d" * 40, "e" * 40, True))  # GitHub's list says merged with merged_at
        self.assertFalse(pulls[self.pr]["merged"])
        self.assertEqual([p["number"] for p in self.repo.pulls("open")], [self.pr])

    def test_the_token_goes_in_the_header(self):
        self.repo.issue(self.i1)
        self.assertEqual(self.gh.requests[-1][2], f"Bearer {self.gh.token}")
        with self.assertRaises(GitHubError):
            GitHubRepo(REPO, token="wrong", api=self.gh.url).issue(self.i1)

    def test_transient_errors_are_retried(self):
        self.gh.failures += [(502, {}), (503, {})]
        self.assertEqual(self.repo.issue(self.i1)["number"], self.i1)
        self.assertEqual(self.sleeps, [1, 2])

    def test_rate_limits_wait_for_the_reset(self):
        self.gh.failures.append((403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1030"}))
        self.gh.failures.append((429, {"Retry-After": "7"}))
        self.assertEqual(self.repo.issue(self.i1)["number"], self.i1)
        self.assertEqual(self.sleeps, [31.0, 7.0])

    def test_a_long_rate_limit_fails_clearly(self):
        self.gh.failures.append((403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "99999"}))
        with self.assertRaises(GitHubError) as e:
            self.repo.issue(self.i1)
        self.assertIn("rate limit", str(e.exception))

    def test_a_plain_403_is_a_permission_error(self):
        self.gh.failures.append((403, {}))
        with self.assertRaises(GitHubError) as e:
            self.repo.issue(self.i1)
        self.assertIn("HTTP 403", str(e.exception))
        self.assertEqual(self.sleeps, [])

    def test_names_must_be_owner_slash_repo(self):
        with self.assertRaises(ValueError):
            GitHubRepo("noslash")


class FakeForgejoClient:
    def __init__(self):
        self.calls = []

    def api(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/comments") and method == "POST":
            return {"id": 1, "body": body["body"], "user": {"login": "bot"}}
        if "/pulls/" in path:
            return {"number": 3, "title": "t", "body": "b", "state": "open", "head": {"sha": "d" * 40},
                    "merged": True}
        if path.endswith("/comments"):
            return []
        if "/issues/" in path:
            return {"number": 1, "title": "t", "body": "b", "state": "open", "labels": [{"name": "bounty"}],
                    "user": {"login": "r"}}
        return [{"number": 1, "title": "t", "body": "b", "state": "open", "labels": [], "user": None}]


class TestHosts(unittest.TestCase):
    def test_forgejo_gives_the_same_shapes(self):
        client = FakeForgejoClient()
        repo = forge.ForgejoRepo(client, "maintainer/sample")
        self.assertEqual(repo.issue(1)["labels"], ["bounty"])
        self.assertEqual(repo.pull(3)["head_sha"], "d" * 40)
        self.assertTrue(repo.merged(3))
        self.assertEqual(repo.issues(label="bounty")[0]["number"], 1)
        self.assertEqual(client.calls[-1][1], "/repos/maintainer/sample/issues?state=open&type=issues&labels=bounty")

    def test_config_picks_the_host_per_repository(self):
        cfg = {"repos": {"acme/demo": {"host": "github", "api": "http://127.0.0.1:1"},
                         "maintainer/sample": {"host": "forgejo", "api": "http://127.0.0.1:3300"}}}
        env = {"GITHUB_TOKEN": "t", "FORGEJO_TOKEN": "f"}
        gh = forge.repo_for("acme/demo", cfg, env)
        self.assertIsInstance(gh, GitHubRepo)
        self.assertEqual((gh.api, gh.token), ("http://127.0.0.1:1", "t"))
        self.assertIsInstance(forge.repo_for("maintainer/sample", cfg, env), forge.ForgejoRepo)
        default = forge.repo_for("other/repo", cfg, {"GITHUB_APP_TOKEN": "app"})
        self.assertEqual((default.api, default.token), ("https://api.github.com", "app"))
        with self.assertRaises(ValueError):
            forge.repo_for("x/y", {"repos": {"x/y": {"host": "gitlab"}}}, env)


if __name__ == "__main__":
    unittest.main()
