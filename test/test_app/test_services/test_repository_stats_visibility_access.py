import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.projects.repository_stats.services.visibility_access import (
    SESSION_KEY,
    UPN_ATTRIBUTE,
    GitHubAccessCheckError,
    clear_saml_email_map_cache,
    fetch_saml_email_map,
    get_username_by_email,
    is_team_member,
    parse_team,
    resolve_github_username,
    user_has_stats_access,
    verified_work_email,
)

TEAM = "ministryofjustice/repository-stats-viewers"
MEMBERSHIP_PATH = (
    "/orgs/ministryofjustice/teams/repository-stats-viewers/memberships/octocat"
)


def response(status_code, body=None):
    return SimpleNamespace(status_code=status_code, json=lambda: body or {})


def saml_node(login, email=None, upn=None, username=None, name_id="waad|abc"):
    return {
        "samlIdentity": {
            "nameId": name_id,
            "username": username or name_id,
            "emails": [{"value": email}] if email else [],
            "attributes": [{"name": UPN_ATTRIBUTE, "value": upn}] if upn else [],
        },
        "user": {"login": login} if login else None,
    }


def saml_page(nodes, next_cursor=None):
    return response(
        200,
        {
            "data": {
                "organization": {
                    "samlIdentityProvider": {
                        "externalIdentities": {
                            "pageInfo": {
                                "hasNextPage": next_cursor is not None,
                                "endCursor": next_cursor,
                            },
                            "nodes": nodes,
                        }
                    }
                }
            }
        },
    )


class FakeGitHub:
    """Answers GET paths from a dict, GraphQL from a list of pages; records every call."""

    def __init__(self, responses, graphql_pages=None):
        self.responses = responses
        self.graphql_pages = list(graphql_pages or [])
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        result = self.responses.get(path, response(404))
        if isinstance(result, Exception):
            raise result
        return result

    def graphql(self, query, variables=None):
        self.calls.append(("graphql", (variables or {}).get("cursor")))
        if not self.graphql_pages:
            raise AssertionError("unexpected GraphQL call")
        result = self.graphql_pages.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def user(nickname="octocat", sub="github|583231"):
    userinfo = {
        "sub": sub,
        "name": "The Octocat",
        "picture": "https://example.test/a.png",
    }
    if nickname is not None:
        userinfo["nickname"] = nickname
    return {"access_token": "x", "expires_at": 9999999999, "userinfo": userinfo}


def microsoft_user(
    email="Octo.Cat@justice.gov.uk", email_verified=True, nickname="octo.cat"
):
    userinfo = {"sub": "waad|pairwise-id", "nickname": nickname, "name": "Octo Cat"}
    if email is not None:
        userinfo["email"] = email
    if email_verified is not None:
        userinfo["email_verified"] = email_verified
    return {"access_token": "x", "expires_at": 9999999999, "userinfo": userinfo}


class TestParseTeam(unittest.TestCase):
    def test_values(self):
        self.assertIsNone(parse_team(None))
        self.assertIsNone(parse_team("  "))
        self.assertEqual(
            parse_team("repository-stats-viewers"),
            ("ministryofjustice", "repository-stats-viewers"),
        )
        self.assertEqual(
            parse_team("moj-analytical-services/viewers"),
            ("moj-analytical-services", "viewers"),
        )


class TestIsTeamMember(unittest.TestCase):
    def test_member(self):
        github = FakeGitHub(
            {MEMBERSHIP_PATH: response(200, {"state": "active", "role": "member"})}
        )
        self.assertTrue(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])

    def test_pending_invitation_is_not_membership(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "pending"})})
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_missing_state_fails_closed(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"role": "member"})})
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_non_dict_body_fails_closed(self):
        github = FakeGitHub(
            {MEMBERSHIP_PATH: SimpleNamespace(status_code=200, json=lambda: None)}
        )
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_non_member(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(404)})
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_other_status_raises_without_personal_data(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(500)})
        with self.assertRaises(GitHubAccessCheckError) as raised:
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        self.assertNotIn("octocat", str(raised.exception))
        self.assertNotIn("repository-stats-viewers", str(raised.exception))


class TestResolveGitHubUsername(unittest.TestCase):
    def test_nickname_first(self):
        lookups = []
        self.assertEqual(resolve_github_username(user(), lookups.append), "octocat")
        self.assertEqual(lookups, [])

    def test_falls_back_to_github_id_in_sub(self):
        self.assertEqual(
            resolve_github_username(
                user(nickname=None), lambda github_id: f"login-for-{github_id}"
            ),
            "login-for-583231",
        )
        self.assertEqual(
            resolve_github_username(user(nickname=" "), lambda github_id: "from-id"),
            "from-id",
        )

    def test_unknown_identity(self):
        lookup = lambda github_id: self.fail("should not look up")
        self.assertIsNone(
            resolve_github_username(user(nickname=None, sub="auth0|abc"), lookup)
        )
        self.assertIsNone(
            resolve_github_username(user(nickname=None, sub=None), lookup)
        )
        self.assertIsNone(resolve_github_username({}, lookup))
        self.assertIsNone(resolve_github_username(None, lookup))

    def test_nickname_is_ignored_without_a_github_sub(self):
        lookup = lambda github_id: self.fail("should not look up")
        for sub in ("auth0|abc", "google-oauth2|123", "github|not-a-number", None):
            with self.subTest(sub=sub):
                self.assertIsNone(
                    resolve_github_username(user(nickname="octocat", sub=sub), lookup)
                )


class TestVerifiedWorkEmail(unittest.TestCase):
    def test_verified_moj_email(self):
        for domain in ("justice.gov.uk", "digital.justice.gov.uk"):
            with self.subTest(domain=domain):
                self.assertEqual(
                    verified_work_email(
                        {"email": f" A.B@{domain.upper()} ", "email_verified": True}
                    ),
                    f"a.b@{domain}",
                )
        self.assertEqual(
            verified_work_email(
                {"email": "a@justice.gov.uk", "email_verified": "true"}
            ),
            "a@justice.gov.uk",
        )

    def test_unverified_or_other_domain_is_rejected(self):
        for userinfo in (
            {"email": "a@justice.gov.uk"},
            {"email": "a@justice.gov.uk", "email_verified": False},
            {"email": "a@justice.gov.uk", "email_verified": "false"},
            {"email": "a@justice.gov.uk", "email_verified": 1},
            {"email": "a@example.com", "email_verified": True},
            {"email": "a@evil-justice.gov.uk", "email_verified": True},
            {"email": "a@justice.gov.uk.evil.com", "email_verified": True},
            {"email": "justice.gov.uk", "email_verified": True},
            {"email": "@justice.gov.uk", "email_verified": True},
            {"email": None, "email_verified": True},
            {"email_verified": True},
        ):
            with self.subTest(userinfo=userinfo):
                self.assertIsNone(verified_work_email(userinfo))


class TestFetchSamlEmailMap(unittest.TestCase):
    def test_maps_emails_and_upns_across_pages(self):
        github = FakeGitHub(
            {},
            [
                saml_page(
                    [
                        saml_node("OctoCat", "Octo.Cat@justice.gov.uk"),
                        saml_node(None, "nobody@justice.gov.uk"),
                    ],
                    next_cursor="c1",
                ),
                saml_page(
                    [
                        saml_node("hubot", upn="hubot@digital.justice.gov.uk"),
                        saml_node(
                            "legacy",
                            name_id="legacy.user",
                            username="legacy.user@justice.gov.uk",
                        ),
                    ]
                ),
            ],
        )
        self.assertEqual(
            fetch_saml_email_map("ministryofjustice", github),
            {
                "octo.cat@justice.gov.uk": "octocat",
                "hubot@digital.justice.gov.uk": "hubot",
                "legacy.user@justice.gov.uk": "legacy",
            },
        )
        self.assertEqual(github.calls, [("graphql", None), ("graphql", "c1")])

    def test_email_on_two_logins_maps_to_none(self):
        github = FakeGitHub(
            {},
            [
                saml_page(
                    [
                        saml_node("one", "shared@justice.gov.uk"),
                        saml_node("two", "shared@justice.gov.uk"),
                    ]
                )
            ],
        )
        self.assertEqual(
            fetch_saml_email_map("ministryofjustice", github),
            {"shared@justice.gov.uk": None},
        )

    def test_failures_raise_without_personal_data(self):
        for failure in (
            response(403),
            response(502),
            response(200, {"errors": [{"type": "FORBIDDEN", "message": "x"}]}),
            response(200, {"data": {"organization": {"samlIdentityProvider": None}}}),
            response(200, {"data": {"organization": None}}),
            saml_page([saml_node("octocat", "a@justice.gov.uk")], next_cursor=""),
        ):
            with self.subTest(failure=failure):
                github = FakeGitHub({}, [failure])
                with self.assertRaises(GitHubAccessCheckError) as raised:
                    fetch_saml_email_map("ministryofjustice", github)
                self.assertNotIn("octocat", str(raised.exception))
                self.assertNotIn("justice.gov.uk", str(raised.exception))


class TestGetUsernameByEmail(unittest.TestCase):
    def setUp(self):
        clear_saml_email_map_cache()
        self.addCleanup(clear_saml_email_map_cache)

    def test_org_map_is_cached_until_ttl(self):
        github = FakeGitHub(
            {},
            [
                saml_page([saml_node("octocat", "octo.cat@justice.gov.uk")]),
                saml_page([saml_node("octocat2", "octo.cat@justice.gov.uk")]),
            ],
        )
        module = "app.projects.repository_stats.services.visibility_access"
        with patch(f"{module}.monotonic", return_value=1000.0):
            self.assertEqual(
                get_username_by_email(
                    "Octo.Cat@justice.gov.uk", "ministryofjustice", github
                ),
                "octocat",
            )
            self.assertIsNone(
                get_username_by_email(
                    "other@justice.gov.uk", "MinistryOfJustice", github
                )
            )
        self.assertEqual(len(github.calls), 1)
        with patch(f"{module}.monotonic", return_value=1000.0 + 15 * 60):
            self.assertEqual(
                get_username_by_email(
                    "octo.cat@justice.gov.uk", "ministryofjustice", github
                ),
                "octocat2",
            )
        self.assertEqual(len(github.calls), 2)

    def test_failure_is_not_cached(self):
        github = FakeGitHub(
            {},
            [
                response(500),
                saml_page([saml_node("octocat", "octo.cat@justice.gov.uk")]),
            ],
        )
        with self.assertRaises(GitHubAccessCheckError):
            get_username_by_email(
                "octo.cat@justice.gov.uk", "ministryofjustice", github
            )
        self.assertEqual(
            get_username_by_email(
                "octo.cat@justice.gov.uk", "ministryofjustice", github
            ),
            "octocat",
        )


class TestResolveGitHubUsernameByEmail(unittest.TestCase):
    def test_verified_email_is_looked_up(self):
        lookups = []

        def lookup(email):
            lookups.append(email)
            return "octocat"

        self.assertEqual(
            resolve_github_username(
                microsoft_user(), lambda _: self.fail("no id lookup"), lookup
            ),
            "octocat",
        )
        self.assertEqual(lookups, ["octo.cat@justice.gov.uk"])

    def test_nickname_never_used_for_microsoft_users(self):
        for session_user in (
            microsoft_user(email_verified=False),
            microsoft_user(email_verified=None),
            microsoft_user(email="octocat@example.com"),
            microsoft_user(email=None),
        ):
            with self.subTest(session_user=session_user):
                self.assertIsNone(
                    resolve_github_username(
                        session_user,
                        lambda _: self.fail("no id lookup"),
                        lambda _: self.fail("no email lookup"),
                    )
                )
        self.assertIsNone(
            resolve_github_username(
                microsoft_user(), lambda _: self.fail("no id lookup")
            )
        )

    def test_github_sub_ignores_email(self):
        session_user = user()
        session_user["userinfo"].update(
            email="someone.else@justice.gov.uk", email_verified=True
        )
        self.assertEqual(
            resolve_github_username(
                session_user,
                lambda _: self.fail("no id lookup"),
                lambda _: self.fail("no email lookup"),
            ),
            "octocat",
        )


class TestUserHasStatsAccess(unittest.TestCase):
    def setUp(self):
        patcher = patch(
            "app.projects.repository_stats.services.visibility_access.app_config"
        )
        self.config = patcher.start()
        self.addCleanup(patcher.stop)
        self.config.github.stats_access_team = TEAM
        clear_saml_email_map_cache()
        self.addCleanup(clear_saml_email_map_cache)

    def test_team_unset_always_allows(self):
        for value in (None, ""):
            with self.subTest(value=value):
                self.config.github.stats_access_team = value
                github = FakeGitHub({})
                cache = {}
                self.assertTrue(user_has_stats_access(None, cache=cache, client=github))
                self.assertTrue(
                    user_has_stats_access(user(), cache=cache, client=github)
                )
                self.assertEqual(github.calls, [])
                self.assertEqual(cache, {})

    def test_member_is_allowed_and_cached(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        cache = {}
        self.assertTrue(user_has_stats_access(user(), cache=cache, client=github))
        self.assertTrue(user_has_stats_access(user(), cache=cache, client=github))
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])
        entry = cache[SESSION_KEY]
        self.assertEqual(
            {k: entry[k] for k in ("username", "has_access", "team", "sub")},
            {
                "username": "octocat",
                "has_access": True,
                "team": TEAM,
                "sub": "github|583231",
            },
        )
        self.assertRegex(entry["checked_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_non_member_is_denied_and_cached(self):
        github = FakeGitHub({})
        cache = {}
        self.assertFalse(user_has_stats_access(user(), cache=cache, client=github))
        self.assertFalse(user_has_stats_access(user(), cache=cache, client=github))
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])
        self.assertFalse(cache[SESSION_KEY]["has_access"])

    def test_cache_ignored_for_other_user_or_team(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        cache = {
            SESSION_KEY: {
                "sub": "github|1",
                "username": "someone",
                "team": TEAM,
                "has_access": True,
            }
        }
        self.assertTrue(user_has_stats_access(user(), cache=cache, client=github))
        self.assertEqual(len(github.calls), 1)
        self.assertFalse(
            user_has_stats_access(
                user(), team="ministryofjustice/other", cache=cache, client=github
            )
        )
        self.assertEqual(len(github.calls), 2)

    def test_explicit_team_overrides_config(self):
        self.config.github.stats_access_team = None
        path = "/orgs/moj-analytical-services/teams/analysts/memberships/octocat"
        github = FakeGitHub({path: response(200, {"state": "active"})})
        self.assertTrue(
            user_has_stats_access(
                user(), team="moj-analytical-services/analysts", cache={}, client=github
            )
        )
        self.assertEqual(github.calls, [path])

    def test_sub_fallback_looks_up_login_once(self):
        github = FakeGitHub(
            {
                "/user/583231": response(200, {"login": "octocat"}),
                MEMBERSHIP_PATH: response(200, {"state": "active"}),
            }
        )
        cache = {}
        self.assertTrue(
            user_has_stats_access(user(nickname=None), cache=cache, client=github)
        )
        self.assertTrue(
            user_has_stats_access(user(nickname=None), cache=cache, client=github)
        )
        self.assertEqual(github.calls, ["/user/583231", MEMBERSHIP_PATH])

    def test_unresolvable_user_is_denied(self):
        github = FakeGitHub({})
        for session_user in (
            None,
            {},
            user(nickname=None, sub="auth0|abc"),
            user(nickname=None),
        ):
            with self.subTest(session_user=session_user):
                self.assertFalse(
                    user_has_stats_access(session_user, cache={}, client=github)
                )

    def test_errors_deny_are_not_cached_and_log_no_personal_data(self):
        for failure in (
            response(500),
            response(403),
            ConnectionError("down"),
            ValueError("bad key"),
        ):
            with self.subTest(failure=failure):
                github = FakeGitHub({MEMBERSHIP_PATH: failure})
                cache = {}
                with self.assertLogs(
                    "app.projects.repository_stats.services.visibility_access", "DEBUG"
                ) as logs:
                    self.assertFalse(
                        user_has_stats_access(user(), cache=cache, client=github)
                    )
                self.assertEqual(cache, {})
                output = "\n".join(logs.output)
                self.assertNotIn("octocat", output)
                self.assertNotIn("repository-stats-viewers", output)
                self.assertTrue(
                    all(
                        record.levelname in ("DEBUG", "WARNING")
                        for record in logs.records
                    )
                )

    def test_microsoft_user_in_team_is_allowed_and_cached(self):
        github = FakeGitHub(
            {MEMBERSHIP_PATH: response(200, {"state": "active"})},
            [saml_page([saml_node("octocat", "octo.cat@justice.gov.uk")])],
        )
        cache = {}
        self.assertTrue(
            user_has_stats_access(microsoft_user(), cache=cache, client=github)
        )
        self.assertTrue(
            user_has_stats_access(microsoft_user(), cache=cache, client=github)
        )
        self.assertEqual(github.calls, [("graphql", None), MEMBERSHIP_PATH])
        self.assertEqual(cache[SESSION_KEY]["sub"], "waad|pairwise-id")
        self.assertEqual(cache[SESSION_KEY]["username"], "octocat")
        self.assertTrue(cache[SESSION_KEY]["has_access"])

    def test_microsoft_user_not_in_team_is_denied(self):
        github = FakeGitHub(
            {MEMBERSHIP_PATH: response(404)},
            [saml_page([saml_node("octocat", "octo.cat@justice.gov.uk")])],
        )
        cache = {}
        self.assertFalse(
            user_has_stats_access(microsoft_user(), cache=cache, client=github)
        )
        self.assertFalse(cache[SESSION_KEY]["has_access"])

    def test_microsoft_user_with_untrusted_email_is_denied_without_lookups(self):
        for session_user in (
            microsoft_user(email_verified=False),
            microsoft_user(email_verified=None),
            microsoft_user(email="octocat@example.com"),
            microsoft_user(email=None, nickname="octocat"),
        ):
            with self.subTest(session_user=session_user):
                github = FakeGitHub(
                    {MEMBERSHIP_PATH: response(200, {"state": "active"})}
                )
                cache = {}
                self.assertFalse(
                    user_has_stats_access(session_user, cache=cache, client=github)
                )
                self.assertEqual(github.calls, [])
                self.assertEqual(cache, {})

    def test_microsoft_user_without_github_account_is_denied(self):
        github = FakeGitHub(
            {MEMBERSHIP_PATH: response(200, {"state": "active"})},
            [saml_page([saml_node("someone", "someone@justice.gov.uk")])],
        )
        cache = {}
        self.assertFalse(
            user_has_stats_access(microsoft_user(), cache=cache, client=github)
        )
        self.assertEqual(github.calls, [("graphql", None)])
        self.assertEqual(cache, {})

    def test_microsoft_user_github_errors_deny_and_are_not_cached(self):
        for failure in (
            response(403),
            response(200, {"errors": [{"type": "FORBIDDEN"}]}),
            ConnectionError("down"),
        ):
            with self.subTest(failure=failure):
                clear_saml_email_map_cache()
                github = FakeGitHub(
                    {MEMBERSHIP_PATH: response(200, {"state": "active"})},
                    [
                        failure,
                        saml_page([saml_node("octocat", "octo.cat@justice.gov.uk")]),
                    ],
                )
                cache = {}
                with self.assertLogs(
                    "app.projects.repository_stats.services.visibility_access", "DEBUG"
                ) as logs:
                    self.assertFalse(
                        user_has_stats_access(
                            microsoft_user(), cache=cache, client=github
                        )
                    )
                self.assertEqual(cache, {})
                output = "\n".join(logs.output)
                self.assertNotIn("octo", output.lower())
                self.assertNotIn("repository-stats-viewers", output)
                self.assertTrue(
                    user_has_stats_access(microsoft_user(), cache=cache, client=github)
                )

    def test_uses_flask_session_by_default(self):
        from flask import Flask, session

        app = Flask(__name__)
        app.secret_key = "test"
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        with app.test_request_context():
            self.assertTrue(user_has_stats_access(user(), client=github))
            self.assertTrue(session[SESSION_KEY]["has_access"])


if __name__ == "__main__":
    unittest.main()
