from typing import Any, Dict, List, Tuple, Type
import importlib.resources
import json
from pydantic import BaseModel, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
import os
from pathlib import Path

settings_dir = importlib.resources.files(__name__)

# Default YAML file path (package default)
DEFAULT_YAML_PATH = settings_dir / 'settings.yaml'
# User YAML file path (in current working directory)
USER_YAML_PATH = Path(os.getcwd()) / 'settings.yaml'

# Env vars to ignore (system/shell vars)
IGNORED_ENV_VARS = {
    "PATH", "HOME", "USER", "SHELL", "PWD", "OLDPWD", "TERM", "LANG", "LC_ALL",
    "LC_CTYPE", "EDITOR", "VISUAL", "PAGER", "LESS", "DISPLAY", "SSH_AUTH_SOCK",
    "SSH_AGENT_PID", "GPG_AGENT_INFO", "GNOME_KEYRING_CONTROL", "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP", "XDG_RUNTIME_DIR", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS",
    "DBUS_SESSION_BUS_ADDRESS", "WINDOWID", "COLORTERM", "TERM_PROGRAM",
    "TERM_PROGRAM_VERSION", "VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PS1", "PS2",
    "HOSTNAME", "HOSTTYPE", "OSTYPE", "MACHTYPE", "SHLVL", "_", "LOGNAME",
    "MAIL", "MANPATH", "INFOPATH", "LS_COLORS", "LESSOPEN", "LESSCLOSE",
}


class EnvSettingsSource(PydanticBaseSettingsSource):
    """🌍 Custom source that reads ALL env vars (except system ones) into settings."""

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        """Get value for a defined field from env."""
        env_val = os.environ.get(field_name.upper()) or os.environ.get(field_name)
        if env_val is not None:
            return self._parse_value(env_val), field_name, False
        return None, field_name, False

    def _parse_value(self, value: str) -> Any:
        """🔧 Try to parse JSON, otherwise return as string."""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def __call__(self) -> Dict[str, Any]:
        """📦 Return all env vars as settings dict."""
        result: Dict[str, Any] = {}

        for key, value in os.environ.items():
            # Skip system/shell env vars
            if key in IGNORED_ENV_VARS or key.startswith("_"):
                continue

            result[key] = self._parse_value(value)

        return result


class DynamicModel(BaseModel):
    """🔄 Recursively converts nested dicts to Pydantic objects with dot notation access."""

    model_config = SettingsConfigDict(extra="allow", case_sensitive=True)

    @model_validator(mode="before")
    @classmethod
    def convert_nested_dicts(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively convert nested dicts to DynamicModel instances."""
        if not isinstance(data, dict):
            return data
        return {key: cls._convert_value(value) for key, value in data.items()}

    @classmethod
    def _convert_value(cls, value: Any) -> Any:
        """Convert a single value, recursively handling dicts and lists."""
        if isinstance(value, dict):
            return DynamicModel(**value)
        elif isinstance(value, list):
            return [cls._convert_value(item) for item in value]
        return value

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self) -> List[str]:
        return list(self.model_fields_set | set(self.model_extra.keys() if self.model_extra else []))

    def values(self) -> List[Any]:
        return [getattr(self, k) for k in self.keys()]

    def items(self) -> List[Tuple[str, Any]]:
        return [(k, getattr(self, k)) for k in self.keys()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,  # Allow LOGGING or logging env vars
        extra="allow",
        env_nested_delimiter="__",  # Allow LOGGING__ROOT__LEVEL style env vars
        env_prefix="",  # No prefix - reads env vars directly (e.g., LOGGING, DATABASE_URL)
    )

    logging: DynamicModel = DynamicModel()

    @model_validator(mode="after")
    def convert_extra_dicts_to_dynamic(self) -> "Settings":
        """🔄 Convert any extra dict fields from env/yaml to DynamicModel."""
        if self.model_extra:
            for key, value in self.model_extra.items():
                if isinstance(value, dict):
                    object.__setattr__(self, key, DynamicModel(**value))
        return self

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        📋 Priority order (highest to lowest):
        1. user_yaml - User's settings.yaml in CWD
        2. init_settings - Values passed directly to Settings()
        3. env_settings - ALL environment variables (custom source)
        4. default_yaml - Package default settings.yaml
        """
        sources = []

        # User YAML has highest priority
        if USER_YAML_PATH.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=USER_YAML_PATH))

        sources.append(init_settings)
        sources.append(EnvSettingsSource(settings_cls))  # Custom env source that reads ALL env vars

        # Default YAML has lowest priority
        sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=DEFAULT_YAML_PATH))

        return tuple(sources)


settings = Settings()