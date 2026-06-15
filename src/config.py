from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT_DIR / "config" / "profile.yaml"
DATA_DIR = ROOT_DIR / "data"
EXPORTS_DIR = ROOT_DIR / "exports"
DB_PATH = DATA_DIR / "jobs.db"
SUPPORTED_COUNTRIES = {"gb", "de", "nl", "ie"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AppConfig:
    data: dict[str, Any]
    eligibility_rules: dict[str, Any]

    @property
    def countries(self) -> list[str]:
        return list(self.data["search"]["countries"])

    @property
    def queries(self) -> list[str]:
        return list(self.data.get("queries", []))

    @property
    def recipient(self) -> str | None:
        env_name = self.data["profile"].get("email_recipient_env", "EMAIL_RECIPIENT")
        return os.getenv(env_name)

    def provider(self, name: str) -> dict[str, Any]:
        return dict(self.data.get("providers", {}).get(name, {}))


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"Configuration root must be a mapping: {path}")
    return value


def validate_config(data: dict[str, Any]) -> None:
    for section in ("profile", "search", "providers", "roles", "skills", "salary_preferences"):
        if not isinstance(data.get(section), dict):
            raise ConfigError(f"Missing or invalid configuration section: {section}")

    countries = data["search"].get("countries")
    if not isinstance(countries, list) or not countries:
        raise ConfigError("search.countries must be a non-empty list")
    invalid = set(countries) - SUPPORTED_COUNTRIES
    if invalid:
        raise ConfigError(
            "Phase One supports only gb, de, nl and ie; invalid countries: "
            + ", ".join(sorted(invalid))
        )

    canonical = data["roles"].get("canonical")
    if not isinstance(canonical, dict) or not canonical:
        raise ConfigError("roles.canonical must define at least one role")
    for country in countries:
        salary = data["salary_preferences"].get(country)
        if not isinstance(salary, dict) or not salary.get("currency"):
            raise ConfigError(f"salary_preferences.{country} must define currency")
        if not isinstance(salary.get("preferred_min"), (int, float)):
            raise ConfigError(f"salary_preferences.{country}.preferred_min must be numeric")

    reed_countries = set(data["providers"].get("reed", {}).get("countries", []))
    if reed_countries - {"gb"}:
        raise ConfigError("Reed may only be configured for gb")


def load_config(path: Path = PROFILE_PATH) -> AppConfig:
    data = _read_yaml(path)
    validate_config(data)
    rules_path = Path(data.get("eligibility", {}).get("rules_path", "config/eligibility_rules.yaml"))
    if not rules_path.is_absolute():
        rules_path = ROOT_DIR / rules_path
    return AppConfig(data=data, eligibility_rules=_read_yaml(rules_path))


def load_profile(path: Path = PROFILE_PATH) -> dict[str, Any]:
    """Compatibility wrapper for callers that still expect a dictionary."""
    return load_config(path).data
