"""MyRAG (beta) configuration."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_title: str = Field(default="MyRAG (beta)")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)

    # Database
    database_url: str = Field(default="sqlite+aiosqlite:////app/data/myrag.db")

    # OpenRAG
    openrag_url: str = Field(default="http://openrag:8080")
    openrag_admin_token: str = Field(default="")

    # Keycloak
    keycloak_url: str = Field(default="http://keycloak:8080")
    keycloak_realm: str = Field(default="openwebui")
    keycloak_client_id: str = Field(default="myrag-admin")
    keycloak_client_secret: str = Field(default="")
    keycloak_admin_user: str = Field(default="admin")
    keycloak_admin_password: str = Field(default="")

    # Legifrance PISTE
    legifrance_client_id: str = Field(default="")
    legifrance_client_secret: str = Field(default="")

    # Graph
    graphrag_viewer_url: str = Field(default="")
    myrag_group_root: str = Field(default="/myrag")

    # Public URL (for iframe links)
    myrag_public_url: str = Field(default="http://localhost:8200")

    # Data directory
    data_dir: str = Field(default="/app/data")

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
