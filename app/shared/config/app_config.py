import os
from types import SimpleNamespace


def __get_env_var(name: str) -> str | None:
    return os.getenv(name)


def __get_env_var_as_boolean(name: str, default: bool) -> bool | None:
    value = __get_env_var(name)

    if value is None:
        return default

    if value.lower() == "true":
        return True

    if value.lower() == "false":
        return False

    return default


app_config = SimpleNamespace(
    add_stub_values_to_database=__get_env_var_as_boolean(
        "ADD_STUB_VALUES_TO_DATABASE", default=False
    ),
    auth_enabled=__get_env_var_as_boolean("AUTH_ENABLED", default=True),
    auth0=SimpleNamespace(
        domain=__get_env_var("AUTH0_DOMAIN"),
        client_id=__get_env_var("AUTH0_CLIENT_ID"),
        client_secret=__get_env_var("AUTH0_CLIENT_SECRET"),
    ),
    circleci=SimpleNamespace(
        token=__get_env_var("CIRCLECI_TOKEN"),
        cost_per_credit=float(
            str(__get_env_var("CIRCLECI_COST_PER_CREDIT"))
            if __get_env_var("CIRCLECI_COST_PER_CREDIT")
            else "0.0005"
        ),
    ),
    flask=SimpleNamespace(
        app_secret_key=__get_env_var("APP_SECRET_KEY"),
    ),
    logging_level=__get_env_var("LOGGING_LEVEL"),
    phase_banner_text=__get_env_var("PHASE_BANNER_TEXT"),
    postgres=SimpleNamespace(
        user=__get_env_var("POSTGRES_USER"),
        password=__get_env_var("POSTGRES_PASSWORD"),
        db=__get_env_var("POSTGRES_DB"),
        host=__get_env_var("POSTGRES_HOST"),
        port=__get_env_var("POSTGRES_PORT"),
        sql_alchemy_database_url=(
            f"postgresql://{__get_env_var('POSTGRES_USER')}:{__get_env_var('POSTGRES_PASSWORD')}@"
            f"{__get_env_var('POSTGRES_HOST')}:{__get_env_var('POSTGRES_PORT')}/{__get_env_var('POSTGRES_DB')}"
        ),
    ),
    github=SimpleNamespace(
        app=SimpleNamespace(
            client_id=__get_env_var("GITHUB_APP_CLIENT_ID"),
            installation_id=int(__get_env_var("GITHUB_APP_INSTALLATION_ID") or 0),
            private_key=__get_env_var("GITHUB_APP_PRIVATE_KEY"),
        ),
        token=__get_env_var("ADMIN_GITHUB_TOKEN"),
    ),
    sentry=SimpleNamespace(
        dsn_key=__get_env_var("SENTRY_DSN_KEY"), environment=__get_env_var("SENTRY_ENV")
    ),
)
