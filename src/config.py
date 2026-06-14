import os
from typing import List, Dict, Optional, Any
import yaml
from pydantic import BaseModel, Field, field_validator

class LoginRecipeStep(BaseModel):
    action: str  # "navigate", "fill", "click", "wait_for", "wait_ms"
    url: Optional[str] = None
    selector: Optional[str] = None
    value: Optional[str] = None
    timeout: Optional[int] = None  # in milliseconds

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"navigate", "fill", "click", "wait_for", "wait_ms", "wait_for_url"}
        if v not in allowed:
            raise ValueError(f"action must be one of {allowed}")
        return v

class LoginConfig(BaseModel):
    type: str  # "none", "recipe", "script"
    recipe: Optional[List[LoginRecipeStep]] = Field(default_factory=list)
    script_path: Optional[str] = None
    credentials: Dict[str, Any] = Field(default_factory=dict)
    session_verification_url: Optional[str] = None

    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"none", "recipe", "script"}
        if v not in allowed:
            raise ValueError(f"login type must be one of {allowed}")
        return v

class PageConfig(BaseModel):
    key: str
    name: str
    url: str
    selector: Optional[str] = None
    exclude: List[str] = Field(default_factory=list)
    check_interval_seconds: Optional[int] = None
    save_screenshot: Optional[bool] = None

class GroupConfig(BaseModel):
    name: str
    login: LoginConfig
    pages: List[PageConfig]
    save_screenshot: Optional[bool] = None
    api_handler: Optional[str] = None

class AppConfig(BaseModel):
    discord_webhook_url: str
    check_interval_seconds: int = 1800
    save_screenshots: bool = True
    error_retry_threshold: int = 3
    groups: Dict[str, GroupConfig]

def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load and validate config.yaml."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML file: {e}") from e

    if not data:
        raise ValueError("Configuration file is empty")

    return AppConfig(**data)
