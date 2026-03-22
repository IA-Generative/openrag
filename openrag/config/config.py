from .settings import Settings, get_settings


def load_config(config_path=None, overrides=None) -> Settings:
    """Return the cached Pydantic Settings singleton.

    The ``config_path`` parameter is kept for backward compatibility.
    Use ``OPENRAG_CONF_DIR`` env var to override the config directory.

    The ``overrides`` parameter is supported — pass a dict to override
    specific values (useful for tests).
    """
    if overrides:
        # Bypass cache when overrides are provided (test scenarios)
        from .loader import load_config as _load

        return _load(conf_dir=config_path, overrides=overrides)
    return get_settings()
