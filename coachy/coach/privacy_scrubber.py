"""Privacy scrubber — anonymizes activity text before sending to cloud LLM.

Runs locally (either via a local LLM or regex fallback) so PII never leaves
the machine.
"""
import logging
import os
import pathlib
import re
import shutil
from typing import Optional

from ..app_paths import get_app_dir, get_bundle_resources_dir
from ..config import get_config

logger = logging.getLogger(__name__)

# Default scrubber prompt shipped with the app
_DEFAULT_SCRUBBER_PROMPT = """\
Anonymize the following activity timeline for privacy. Rules:
- Replace all person names with Person_A, Person_B, Person_C (consistent within the text)
- Replace email addresses with [email]
- Replace specific project/company names with Project_X, Project_Y, Org_X
- Replace URLs with [url]
- PRESERVE: app names, activity types, durations, time ranges, engagement levels
- PRESERVE: the structure and meaning of the text
- Return ONLY the anonymized text, no explanations.
"""


def get_scrubber_prompt_path() -> pathlib.Path:
    """Return path to the user-editable scrubber prompt file."""
    return get_app_dir() / "scrubber_prompt.md"


def _ensure_scrubber_prompt() -> pathlib.Path:
    """Ensure scrubber_prompt.md exists, copying from example if needed."""
    prompt_path = get_scrubber_prompt_path()
    if prompt_path.exists():
        return prompt_path

    # Try to copy from bundle resources
    example_src = get_bundle_resources_dir() / "scrubber_prompt.md.example"
    if example_src.exists():
        shutil.copy2(str(example_src), str(prompt_path))
    else:
        # Write default directly
        prompt_path.write_text(_DEFAULT_SCRUBBER_PROMPT)

    logger.info(f"Created scrubber prompt: {prompt_path}")
    return prompt_path


class PrivacyScrubber:
    """Anonymizes activity timeline text before it reaches a cloud API.

    Supports three modes:
      - "mlx":   Local MLX model (Apple Silicon optimized)
      - "local": Local OpenAI-compatible endpoint (LM Studio, Ollama, etc.)
      - "regex": Simple regex-based scrubbing (no model needed)
    """

    def __init__(self, config=None):
        self._config = config or get_config()
        self._prompt_template = self._load_prompt()
        self._mode = self._config.get("privacy.scrubber_model", "regex")
        self._local_client = None

    # ---- public API -------------------------------------------------------

    def scrub(self, activity_text: str) -> str:
        """Scrub PII from activity text.

        Tries the configured model first, falls back to regex on error.

        Args:
            activity_text: Raw activity timeline text.

        Returns:
            Anonymized text.
        """
        if not activity_text or not activity_text.strip():
            return activity_text

        if self._mode in ("mlx", "local"):
            try:
                return self._scrub_with_model(activity_text)
            except Exception as e:
                logger.warning(f"Model scrubbing failed, falling back to regex: {e}")
                return self._scrub_with_regex(activity_text)
        else:
            return self._scrub_with_regex(activity_text)

    # ---- prompt loading ---------------------------------------------------

    def _load_prompt(self) -> str:
        """Load scrubber prompt from user file or default."""
        prompt_rel = self._config.get("privacy.scrubber_prompt_path", "scrubber_prompt.md")
        prompt_path = get_app_dir() / prompt_rel
        if prompt_path.exists():
            try:
                return prompt_path.read_text().strip()
            except Exception as e:
                logger.warning(f"Failed to read scrubber prompt: {e}")

        return _DEFAULT_SCRUBBER_PROMPT.strip()

    # ---- model-based scrubbing --------------------------------------------

    def _get_local_client(self):
        """Lazy-init a local LLM client for scrubbing."""
        if self._local_client is not None:
            return self._local_client

        from .llm import LocalLLMClient, MLXClient, LLMError

        if self._mode == "mlx":
            model_path = self._config.get("coach.mlx.model_path")
            if not model_path:
                raise LLMError("MLX model_path not configured for scrubber")
            self._local_client = MLXClient(model_path=model_path)
        elif self._mode == "local":
            endpoint = self._config.get("coach.local_llm.endpoint", "http://localhost:8080/v1")
            model = self._config.get("coach.local_llm.model", "default")
            self._local_client = LocalLLMClient(endpoint=endpoint, model=model)
        else:
            raise ValueError(f"No local model for mode: {self._mode}")

        return self._local_client

    def _scrub_with_model(self, text: str) -> str:
        """Scrub using a local LLM."""
        client = self._get_local_client()
        prompt = f"{self._prompt_template}\n\n---\n\n{text}"

        response = client.generate_text(
            prompt=prompt,
            max_tokens=len(text) // 2 + 500,  # generous but bounded
            temperature=0.1,  # deterministic
        )

        result = response.get("content", "").strip()
        if not result:
            logger.warning("Model returned empty scrub result, using regex fallback")
            return self._scrub_with_regex(text)

        return result

    # ---- regex-based scrubbing -------------------------------------------

    @staticmethod
    def _scrub_with_regex(text: str) -> str:
        """Scrub PII using regex patterns.

        Catches the most common PII patterns: emails, phone numbers, URLs,
        and capitalised multi-word names that look like person names.
        """
        # Email addresses
        text = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '[email]',
            text,
        )

        # Phone numbers (various formats)
        text = re.sub(
            r'\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b',
            '[phone]',
            text,
        )

        # URLs (http/https)
        text = re.sub(
            r'https?://[^\s<>"{}|\\^`\[\]]+',
            '[url]',
            text,
        )

        # IP addresses
        text = re.sub(
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            '[ip]',
            text,
        )

        # File paths that might reveal project structure
        # (leave app names like "VS Code" alone, only scrub full paths)
        text = re.sub(
            r'(?:/Users/[^\s:]+)',
            '[path]',
            text,
        )

        return text
