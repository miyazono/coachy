"""macOS Keychain storage for API keys via the keyring library."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_NAME = "Coachy"
ACCOUNT_API_KEY = "anthropic_api_key"

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False


def _require_keyring():
    if not _KEYRING_AVAILABLE:
        raise RuntimeError("keyring library not installed. Install with: pip install keyring")


def get_api_key() -> Optional[str]:
    """Retrieve the Anthropic API key from the macOS Keychain.

    Returns:
        The API key string, or None if not stored.
    """
    if not _KEYRING_AVAILABLE:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, ACCOUNT_API_KEY)
    except Exception as e:
        logger.warning(f"Failed to read API key from Keychain: {e}")
        return None


def set_api_key(key: str) -> None:
    """Store the Anthropic API key in the macOS Keychain.

    Args:
        key: The API key to store.
    """
    _require_keyring()
    keyring.set_password(SERVICE_NAME, ACCOUNT_API_KEY, key)
    logger.info("API key saved to Keychain")


def delete_api_key() -> None:
    """Remove the Anthropic API key from the macOS Keychain."""
    _require_keyring()
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_API_KEY)
        logger.info("API key removed from Keychain")
    except keyring.errors.PasswordDeleteError:
        pass  # already absent


def has_api_key() -> bool:
    """Check whether an API key is stored in the Keychain."""
    return get_api_key() is not None
