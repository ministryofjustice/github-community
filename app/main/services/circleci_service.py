from typing import List

import requests
from app.main.config.app_config import app_config
from app.main.repositories.asset_repository import AssetView
from flask import g


class CircleCIProjectMetricsView:
    def __init__(self, org_project_data: dict):
        self.project_name = org_project_data["project_name"]
        self.total_credits_used = float(
            org_project_data["metrics"]["total_credits_used"]
        )
        self.approximate_cost = (
            self.total_credits_used * app_config.circleci.cost_per_credit
        )


class CircleCIService:
    def __init__(self):
        self.api_token = app_config.circleci.token

    def get_circleci_project_metrics_for_repositories(
        self,
        repositories: List[AssetView],
    ) -> List[CircleCIProjectMetricsView]:
        repository_names = [repository.name for repository in repositories]
        response = requests.get(
            "https://circleci.com/api/v2/insights/gh/ministryofjustice/summary",
            params={
                "reporting-window": "last-30-days",
            },
            headers={"Circle-Token": self.api_token},
        )
        response_json = response.json()
        org_project_data = response_json["org_project_data"]
        filtered_org_project_data = [
            CircleCIProjectMetricsView(project)
            for project in org_project_data
            if project["project_name"] in repository_names
        ]

        return filtered_org_project_data

    def get_total_cost_of_projects(
        self, projects: List[CircleCIProjectMetricsView]
    ) -> int:
        total_credits_used = sum(
            [float(project.total_credits_used) for project in projects]
        )
        total_cost = total_credits_used * app_config.circleci.cost_per_credit
        return total_cost


def get_circleci_service() -> CircleCIService:
    if "circleci_service" not in g:
        g.circleci_service = CircleCIService()
    return g.circleci_service
