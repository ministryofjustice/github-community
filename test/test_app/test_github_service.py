import unittest
from threading import Barrier, Lock, get_ident
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.projects.repository_standards.services.github_service import GithubService

MODULE = "app.projects.repository_standards.services.github_service"


class TestGithubService(unittest.TestCase):
    def test_concurrency_uses_separate_workers_and_preserves_order(self):
        service = GithubService.__new__(GithubService)
        service.organisation_name = "ministryofjustice"
        service._request_coordinator = Mock(request_count=0, request_seconds=0)
        service.github_client_core_api = Mock()
        repositories = [
            SimpleNamespace(name=f"repo-{index}", archived=False, fork=False)
            for index in range(3)
        ]
        service.github_client_core_api.get_organization.return_value.get_repos.return_value = repositories
        rendezvous = Barrier(3, timeout=5)
        registry_lock = Lock()
        threads = set()
        parent_caches = set()
        maintainer_caches = set()
        workers = []

        def new_worker():
            worker = Mock()
            worker.github_client_core_api.get_repo.side_effect = lambda name, lazy: name

            def collect(repo, ignored, parents, maintainers):
                with registry_lock:
                    threads.add(get_ident())
                    parent_caches.add(id(parents))
                    maintainer_caches.add(id(maintainers))
                rendezvous.wait()
                return repo

            worker._collect_repository.side_effect = collect
            with registry_lock:
                workers.append(worker)
            return worker

        with patch.object(service, "_new_worker_service", side_effect=new_worker):
            result = service.get_repositories(workers=3)

        self.assertEqual(result, [f"ministryofjustice/repo-{index}" for index in range(3)])
        self.assertEqual(len(threads), 3)
        self.assertEqual(len(workers), 3)
        self.assertEqual(len(parent_caches), 3)
        self.assertEqual(len(maintainer_caches), 3)
        for worker in workers:
            worker.github_client_core_api.close.assert_called_once()
            worker.github_client.session.close.assert_called_once()

    def test_workers_construct_independent_clients_with_shared_coordinator(self):
        with (
            patch(f"{MODULE}.Auth.AppAuth"),
            patch(f"{MODULE}.Github", side_effect=[Mock(), Mock(), Mock()]),
            patch(f"{MODULE}.GitHubClient", side_effect=[Mock(), Mock(), Mock()]),
        ):
            service = GithubService("client", "key", 123)
            first = service._new_worker_service()
            second = service._new_worker_service()
        self.assertIsNot(first.github_client_core_api, second.github_client_core_api)
        self.assertIsNot(first.github_client, second.github_client)
        self.assertIsNot(first.github_client.session, second.github_client.session)
        self.assertIs(first._request_coordinator, second._request_coordinator)
        self.assertIs(first._request_coordinator, service._request_coordinator)

    def test_worker_failure_is_propagated_and_clients_are_closed(self):
        service = GithubService.__new__(GithubService)
        service.organisation_name = "ministryofjustice"
        service._request_coordinator = Mock()
        worker = Mock()
        worker._collect_repository.side_effect = RuntimeError("Collection failed")
        with patch.object(service, "_new_worker_service", return_value=worker):
            with self.assertRaisesRegex(RuntimeError, "Collection failed"):
                service._collect_concurrently([SimpleNamespace(name="repo")], [], 3)
        worker.github_client_core_api.close.assert_called_once()
        worker.github_client.session.close.assert_called_once()

    def test_concurrency_preserves_scope_and_limit(self):
        service = GithubService.__new__(GithubService)
        service.organisation_name = "ministryofjustice"
        service.github_client_core_api = Mock()
        service._request_coordinator = Mock(request_count=0, request_seconds=0)
        repositories = [
            SimpleNamespace(name="archived", archived=True, fork=False),
            SimpleNamespace(name="fork", archived=False, fork=True),
            SimpleNamespace(name="first", archived=False, fork=False),
            SimpleNamespace(name="second", archived=False, fork=False),
        ]
        service.github_client_core_api.get_organization.return_value.get_repos.return_value = repositories
        with patch.object(service, "_collect_concurrently", return_value=["result"]) as collect:
            self.assertEqual(
                service.get_repositories(limit=1, workers=3, visibility="all"), ["result"]
            )
        collect.assert_called_once_with([repositories[2]], unittest.mock.ANY, 3)
        service.github_client_core_api.get_organization.return_value.get_repos.assert_called_once_with(
            type="all"
        )

    def test_default_scope_is_public_and_excludes_archived_and_forked(self):
        service = GithubService.__new__(GithubService)
        service.organisation_name = "ministryofjustice"
        service.github_client_core_api = Mock()
        service._request_coordinator = Mock(request_count=0, request_seconds=0)
        repositories = [
            SimpleNamespace(name="public", archived=False, fork=False),
            SimpleNamespace(name="archived", archived=True, fork=False),
            SimpleNamespace(name="fork", archived=False, fork=True),
        ]
        service.github_client_core_api.get_organization.return_value.get_repos.return_value = repositories
        with patch.object(service, "_collect_repository", side_effect=lambda repo, *args: repo.name):
            result = service.get_repositories(workers=1)
        self.assertEqual(result, ["public"])
        service.github_client_core_api.get_organization.return_value.get_repos.assert_called_once_with(
            type="public"
        )

    def test_invalid_worker_counts_are_rejected_before_collection(self):
        service = GithubService.__new__(GithubService)
        for workers in (0, -1, 9):
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                service.get_repositories(workers=workers)

    def test_caches_maintainer_count_and_passes_it_to_factory(self):
        service = GithubService.__new__(GithubService)
        service.organisation_name = "ministryofjustice"
        service.github_client_core_api = Mock()
        service.github_client = Mock()
        service.github_client.get_team_maintainer_count.return_value = 2

        repositories = [
            SimpleNamespace(name="repo-one", archived=False, fork=False),
            SimpleNamespace(name="repo-two", archived=False, fork=False),
        ]
        organization = service.github_client_core_api.get_organization.return_value
        organization.get_repos.return_value = repositories

        with (
            patch.object(
                service,
                "_GithubService__get_teams_with_access",
                return_value=(["team-alpha"], [], ["team-alpha"], []),
            ),
            patch(
                "app.projects.repository_standards.services.github_service.RepositoryInfoFactory.from_github_repo",
                side_effect=lambda repo, *args: repo.name,
            ) as factory,
        ):
            result = service.get_repositories()

        self.assertEqual(result, ["repo-one", "repo-two"])
        service.github_client.get_team_maintainer_count.assert_called_once_with(
            "team-alpha"
        )
        self.assertEqual(
            [factory_call.args[-1] for factory_call in factory.call_args_list],
            [{"team-alpha": 2}, {"team-alpha": 2}],
        )