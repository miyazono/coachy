"""Configuration management for Coachy."""
import os
import pathlib
from typing import Any, Dict, List
import yaml


class Config:
    """Configuration handler for Coachy."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize configuration from YAML file.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = pathlib.Path(config_path)
        self._config = self._load_config()
        self._ensure_data_directories()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if config is None:
            raise ValueError(f"Invalid or empty configuration file: {self.config_path}")
            
        return config
    
    def _ensure_data_directories(self) -> None:
        """Create data directories if they don't exist."""
        screenshots_path = pathlib.Path(self.get('storage.screenshots_path'))
        screenshots_path.mkdir(parents=True, exist_ok=True)
        
        db_path = pathlib.Path(self.get('storage.db_path'))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        log_path = pathlib.Path(self.get('logging.file'))
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
        """Database file path."""
        return self.get('storage.db_path', 'data/coachy.db')
    
    @property
    def screenshots_path(self) -> str:
        """Screenshots directory path."""
        return self.get('storage.screenshots_path', 'data/screenshots')
    
    @property
    def retention_days(self) -> int:
        """Retention period in days."""
        return self.get('storage.retention_days', 30)
    
    @property
    def log_file(self) -> str:
        """Log file path."""
        return self.get('logging.file', 'data/logs/coachy.log')
    
    @property
    def log_level(self) -> str:
        """Log level."""
        return self.get('logging.level', 'INFO')


# Global configuration instance
_config_instance = None


def get_config(config_path: str = "config.yaml") -> Config:
    """Get global configuration instance.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance


def get(key: str, default: Any = None) -> Any:
    """Convenience function to get configuration value.
    
    Args:
        key: Configuration key in dot notation
        default: Default value if key not found
        
    Returns:
        Configuration value
    """
    return get_config().get(key, default)