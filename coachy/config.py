"""Configuration management for Coachy."""
import logging
import os
import pathlib
import shutil
from typing import Any, Dict, List
import yaml

from .app_paths import get_config_path, get_config_example_path, get_app_dir

logger = logging.getLogger(__name__)


class Config:
    """Configuration handler for Coachy."""

    def __init__(self, config_path: str = None):
        """Initialize configuration from YAML file.

        Args:
            config_path: Path to configuration file (default: app_paths location)
        """
        if config_path is None:
            self.config_path = get_config_path()
        else:
            self.config_path = pathlib.Path(config_path)
        self._config = self._load_config()
        self._ensure_data_directories()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file.

        If config.yaml doesn't exist but config.yaml.example does,
        copies the example as a starting point. Checks both the config
        directory and the bundle resources directory for the example.
        """
        if not self.config_path.exists():
            # Try sibling example first, then bundle resources
            example_path = self.config_path.parent / (self.config_path.name + '.example')
            if not example_path.exists():
                example_path = get_config_example_path()
            if example_path.exists():
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(example_path), str(self.config_path))
                logger.info(f"Created {self.config_path} from {example_path}")
            else:
                raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        if config is None:
            raise ValueError(f"Invalid or empty configuration file: {self.config_path}")

        return config
    
    def _resolve_path(self, relative_path: str) -> pathlib.Path:
        """Resolve a config path relative to the app data directory.

        Absolute paths are returned as-is. Relative paths are resolved
        against ~/Library/Application Support/Coachy/.
        """
        p = pathlib.Path(relative_path)
        if p.is_absolute():
            return p
        return get_app_dir() / p

    def _ensure_data_directories(self) -> None:
        """Create data directories if they don't exist."""
        screenshots_path = self._resolve_path(self.get('storage.screenshots_path'))
        screenshots_path.mkdir(parents=True, exist_ok=True)

        db_path = self._resolve_path(self.get('storage.db_path'))
        db_path.parent.mkdir(parents=True, exist_ok=True)

        log_path = self._resolve_path(self.get('logging.file'))
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation (e.g., 'capture.interval_seconds')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    @property
    def capture_enabled(self) -> bool:
        """Whether capture is enabled."""
        return self.get('capture.enabled', False)
    
    @property
    def capture_interval(self) -> int:
        """Capture interval in seconds."""
        return self.get('capture.interval_seconds', 60)
    
    @property
    def capture_monitors(self) -> str:
        """Monitor capture setting."""
        return self.get('capture.monitors', 'primary')
    
    @property
    def excluded_apps(self) -> List[str]:
        """List of excluded application names."""
        return self.get('capture.excluded_apps', [])
    
    @property
    def excluded_titles(self) -> List[str]:
        """List of excluded window titles."""
        return self.get('capture.excluded_titles', [])
    
    @property
    def db_path(self) -> str:
        """Database file path (resolved to absolute)."""
        return str(self._resolve_path(self.get('storage.db_path', 'data/coachy.db')))

    @property
    def screenshots_path(self) -> str:
        """Screenshots directory path (resolved to absolute)."""
        return str(self._resolve_path(self.get('storage.screenshots_path', 'data/screenshots')))
    
    @property
    def retention_days(self) -> int:
        """Retention period in days."""
        return self.get('storage.retention_days', 30)
    
    @property
    def log_file(self) -> str:
        """Log file path (resolved to absolute)."""
        return str(self._resolve_path(self.get('logging.file', 'data/logs/coachy.log')))
    
    @property
    def log_level(self) -> str:
        """Log level."""
        return self.get('logging.level', 'INFO')

    @property
    def privacy_level(self) -> str:
        """Privacy level for API prompts: 'private' or 'detailed'."""
        level = self.get('coach.privacy_level', 'private')
        if level not in ('private', 'detailed'):
            logger.warning(f"Unknown privacy_level '{level}', defaulting to 'private'")
            return 'private'
        return level

    @property
    def scrubber_enabled(self) -> bool:
        """Whether the privacy scrubber is enabled."""
        return self.get('privacy.scrubber_enabled', True)

    @property
    def scrubber_model(self) -> str:
        """Scrubber mode: 'mlx', 'local', or 'regex'."""
        return self.get('privacy.scrubber_model', 'regex')

    @property
    def scrubber_prompt_path(self) -> str:
        """Path to scrubber prompt file (relative to app dir)."""
        return self.get('privacy.scrubber_prompt_path', 'scrubber_prompt.md')


# Global configuration instance
_config_instance = None


def get_config(config_path: str = None) -> Config:
    """Get global configuration instance.

    Args:
        config_path: Path to configuration file (default: app_paths location)

    Returns:
        Configuration instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance


def reset_config() -> None:
    """Reset the global configuration instance.

    Call after modifying config.yaml so the next get_config() re-reads it.
    """
    global _config_instance
    _config_instance = None


def get(key: str, default: Any = None) -> Any:
    """Convenience function to get configuration value.
    
    Args:
        key: Configuration key in dot notation
        default: Default value if key not found
        
    Returns:
        Configuration value
    """
    return get_config().get(key, default)