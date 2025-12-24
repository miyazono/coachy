"""Data models and SQLite schema for Coachy."""
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any


# Activity categories with their descriptions and signals
CATEGORIES = {
    "deep_work": {
        "description": "Focused coding, writing, research, analysis",
        "signals": ["VS Code", "PyCharm", "Obsidian", "Notion", "Google Docs", "Overleaf"]
    },
    "communication": {
        "description": "Email, messaging, async communication",
        "signals": ["Mail", "Gmail", "Superhuman", "Slack", "Discord", "Messages"]
    },
    "meetings": {
        "description": "Video calls, meetings (detected by window, not captured)",
        "signals": ["Zoom", "Meet", "Teams", "Webex"]
    },
    "research": {
        "description": "Reading, learning, information gathering",
        "signals": ["Arc", "Chrome", "Safari", "Firefox", "PDF Expert", "Preview"]
    },
    "social_media": {
        "description": "Twitter, LinkedIn, Reddit, etc.",
        "signals": ["twitter.com", "x.com", "linkedin.com", "reddit.com", "news.ycombinator.com"]
    },
    "administrative": {
        "description": "Calendar, task management, file management",
        "signals": ["Calendar", "Notion Calendar", "Finder", "Things", "Todoist"]
    },
    "break": {
        "description": "Entertainment, relaxation",
        "signals": ["YouTube", "Netflix", "Spotify", "Music", "Photos"]
    },
    "unknown": {
        "description": "Unclassified activity",
        "signals": []
    }
}


@dataclass
class ActivityEntry:
    """Represents a single activity log entry."""
    timestamp: int  # Unix timestamp
    datetime_local: str  # ISO format for readability
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    category: str = "unknown"
    ocr_text: Optional[str] = None
    screenshot_path: Optional[str] = None
    duration_seconds: int = 60  # Default to capture interval
    metadata: Optional[Dict[str, Any]] = None
    id: Optional[int] = None  # Set when loaded from database
    
    @classmethod
    def create_now(
        cls,
        app_name: Optional[str] = None,
        window_title: Optional[str] = None,
        category: str = "unknown",
        ocr_text: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        duration_seconds: int = 60,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "ActivityEntry":
        """Create an ActivityEntry with current timestamp."""
        now = time.time()
        timestamp = int(now)
        datetime_local = datetime.fromtimestamp(now).isoformat()
        
        return cls(
            timestamp=timestamp,
            datetime_local=datetime_local,
            app_name=app_name,
            window_title=window_title,
            category=category,
            ocr_text=ocr_text,
            screenshot_path=screenshot_path,
            duration_seconds=duration_seconds,
            metadata=metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            'timestamp': self.timestamp,
            'datetime_local': self.datetime_local,
            'app_name': self.app_name,
            'window_title': self.window_title,
            'category': self.category,
            'ocr_text': self.ocr_text,
            'screenshot_path': self.screenshot_path,
            'duration_seconds': self.duration_seconds,
            'metadata': json.dumps(self.metadata) if self.metadata else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActivityEntry":
        """Create ActivityEntry from database row."""
        metadata = None
        if data.get('metadata'):
            try:
                metadata = json.loads(data['metadata'])
            except json.JSONDecodeError:
                metadata = None
        
        return cls(
            id=data.get('id'),
            timestamp=data['timestamp'],
            datetime_local=data['datetime_local'],
            app_name=data.get('app_name'),
            window_title=data.get('window_title'),
            category=data.get('category', 'unknown'),
            ocr_text=data.get('ocr_text'),
            screenshot_path=data.get('screenshot_path'),
            duration_seconds=data.get('duration_seconds', 60),
            metadata=metadata
        )


@dataclass
class DigestEntry:
    """Represents a coaching digest."""
    generated_at: int  # Unix timestamp
    period_start: int  # Unix timestamp
    period_end: int  # Unix timestamp
    period_type: str  # "day" or "week"
    persona: str  # Coach persona name
    content: str  # Digest text
    token_usage: Optional[Dict[str, int]] = None
    id: Optional[int] = None  # Set when loaded from database
    
    @classmethod
    def create_now(
        cls,
        period_start: int,
        period_end: int,
        period_type: str,
        persona: str,
        content: str,
        token_usage: Optional[Dict[str, int]] = None
    ) -> "DigestEntry":
        """Create a DigestEntry with current timestamp."""
        return cls(
            generated_at=int(time.time()),
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            persona=persona,
            content=content,
            token_usage=token_usage
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            'generated_at': self.generated_at,
            'period_start': self.period_start,
            'period_end': self.period_end,
            'period_type': self.period_type,
            'persona': self.persona,
            'content': self.content,
            'token_usage': json.dumps(self.token_usage) if self.token_usage else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DigestEntry":
        """Create DigestEntry from database row."""
        token_usage = None
        if data.get('token_usage'):
            try:
                token_usage = json.loads(data['token_usage'])
            except json.JSONDecodeError:
                token_usage = None
        
        return cls(
            id=data.get('id'),
            generated_at=data['generated_at'],
            period_start=data['period_start'],
            period_end=data['period_end'],
            period_type=data['period_type'],
            persona=data['persona'],
            content=data['content'],
            token_usage=token_usage
        )


# SQL schema for database initialization
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,              -- Unix timestamp
    datetime_local TEXT NOT NULL,            -- ISO format for readability
    app_name TEXT,                           -- Active application
    window_title TEXT,                       -- Window title
    category TEXT,                           -- Classified category
    ocr_text TEXT,                           -- Extracted text (truncated)
    screenshot_path TEXT,                    -- Path to screenshot file
    duration_seconds INTEGER DEFAULT 60,     -- Time attributed to this capture
    metadata JSON                            -- Extensible metadata
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON activity_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_category ON activity_log(category);
CREATE INDEX IF NOT EXISTS idx_app_name ON activity_log(app_name);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at INTEGER NOT NULL,
    period_start INTEGER NOT NULL,
    period_end INTEGER NOT NULL,
    period_type TEXT NOT NULL,               -- "day" or "week"
    persona TEXT NOT NULL,
    content TEXT NOT NULL,
    token_usage JSON
);

CREATE INDEX IF NOT EXISTS idx_digest_period ON digests(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_digest_persona ON digests(persona);
"""