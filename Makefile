.PHONY: run creation-migration test test-reports

run:
	flask --app app.app --debug run

creation-migration:
	alembic revision --message 'project_name_description'

test:
	coverage run -m pytest

test-reports:
	coverage report --omit=./test/** --sort=cover --show-missing --skip-empty
