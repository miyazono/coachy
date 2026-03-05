"""User-friendly error messages for the menu bar app."""


def friendly_error(exc: Exception) -> str:
    """Map common exceptions to plain-English messages.

    Args:
        exc: The exception to translate.

    Returns:
        A short, non-technical message suitable for a macOS notification.
    """
    msg = str(exc).lower()

    # API key issues
    if "api key" in msg or "authentication" in msg or "401" in msg:
        return "API key is missing or invalid. Open Settings to add your Anthropic key."

    # Network errors
    if any(k in msg for k in ("connection", "timeout", "network", "resolve", "dns")):
        return "Network error. Check your internet connection and try again."

    # Screen recording permission
    if "screen" in msg and ("permission" in msg or "denied" in msg or "capture" in msg):
        return (
            "Screen Recording permission required. "
            "Open System Settings > Privacy & Security > Screen Recording and enable Coachy."
        )

    # Disk space
    if "disk" in msg or "no space" in msg or "enospc" in msg:
        return "Not enough disk space. Run cleanup from Settings or free up disk space."

    # Rate limiting
    if "rate" in msg and "limit" in msg or "429" in msg:
        return "API rate limit reached. Wait a few minutes and try again."

    # Generic API errors
    if "api" in msg and "error" in msg:
        return f"API error: {exc}"

    # Fallback
    return f"Something went wrong: {exc}"
