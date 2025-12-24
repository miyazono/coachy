"""SQLite database operations for Coachy."""
import logging
import pathlib
import sqlite3
import threading
from contextlib import contextmanager
from typing import List, Optional, Dict, Any

from .models import ActivityEntry, DigestEntry, SCHEMA_SQL

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Exception raised for database operation errors."""
    pass


class Database:
    """SQLite database manager for Coachy."""
    
    def __init__(self, db_path: str):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = pathlib.Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._initialize_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        
        return self._local.connection
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _initialize_database(self) -> None:
        """Create database tables if they don't exist."""
        try:
            with self.transaction() as conn:
                conn.executescript(SCHEMA_SQL)
            logger.info(f"Database initialized: {self.db_path}")
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to initialize database: {e}") from e
    
    def insert_activity(self, activity: ActivityEntry) -> int:
        """Insert activity entry into database.
        
        Args:
            activity: ActivityEntry to insert
            
        Returns:
            ID of inserted row
            
        Raises:
            DatabaseError: If insertion fails
        """
        try:
            with self.transaction() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO activity_log (
                        timestamp, datetime_local, app_name, window_title,
                        category, ocr_text, screenshot_path, duration_seconds, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        activity.timestamp,
                        activity.datetime_local,
                        activity.app_name,
                        activity.window_title,
                        activity.category,
                        activity.ocr_text,
                        activity.screenshot_path,
                        activity.duration_seconds,
                        activity.to_dict()['metadata']
                    )
                )
                return cursor.lastrowid
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to insert activity: {e}") from e
    
    def get_activity_by_timerange(
        self,
        start_timestamp: int,
        end_timestamp: int,
        limit: Optional[int] = None
    ) -> List[ActivityEntry]:
        """Get activity entries within time range.
        
        Args:
            start_timestamp: Start time (Unix timestamp)
            end_timestamp: End time (Unix timestamp)
            limit: Maximum number of entries to return
            
        Returns:
            List of ActivityEntry objects
        """
        try:
            conn = self._get_connection()
            query = """
                SELECT * FROM activity_log 
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """
            if limit:
                query += f" LIMIT {limit}"
            
            cursor = conn.execute(query, (start_timestamp, end_timestamp))
            rows = cursor.fetchall()
            
            return [ActivityEntry.from_dict(dict(row)) for row in rows]
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to query activities: {e}") from e
    
    def get_activity_count(self) -> int:
        """Get total number of activity entries.
        
        Returns:
            Number of activity entries in database
        """
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT COUNT(*) FROM activity_log")
            return cursor.fetchone()[0]
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to count activities: {e}") from e
    
    def get_activity_summary(self, start_timestamp: int, end_timestamp: int) -> Dict[str, Any]:
        """Get aggregated activity statistics for a time period.
        
        Args:
            start_timestamp: Start time (Unix timestamp)
            end_timestamp: End time (Unix timestamp)
            
        Returns:
            Dictionary with activity summary statistics
        """
        try:
            conn = self._get_connection()
            
            # Total tracked time
            total_cursor = conn.execute(
                """
                SELECT SUM(duration_seconds) as total_seconds
                FROM activity_log 
                WHERE timestamp >= ? AND timestamp <= ?
                """,
                (start_timestamp, end_timestamp)
            )
            total_seconds = total_cursor.fetchone()[0] or 0
            total_minutes = total_seconds // 60
            
            # By category
            category_cursor = conn.execute(
                """
                SELECT category, SUM(duration_seconds) as seconds
                FROM activity_log 
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY category
                ORDER BY seconds DESC
                """,
                (start_timestamp, end_timestamp)
            )
            
            by_category = {}
            for row in category_cursor:
                minutes = row[1] // 60
                percentage = (minutes / total_minutes * 100) if total_minutes > 0 else 0
                by_category[row[0]] = {
                    "minutes": minutes,
                    "percentage": round(percentage, 1)
                }
            
            # By app
            app_cursor = conn.execute(
                """
                SELECT app_name, category, SUM(duration_seconds) as seconds
                FROM activity_log 
                WHERE timestamp >= ? AND timestamp <= ? AND app_name IS NOT NULL
                GROUP BY app_name, category
                ORDER BY seconds DESC
                LIMIT 10
                """,
                (start_timestamp, end_timestamp)
            )
            
            by_app = {}
            for row in app_cursor:
                minutes = row[2] // 60
                by_app[row[0]] = {
                    "minutes": minutes,
                    "category": row[1]
                }
            
            # Hourly timeline for visualization
            timeline = self._get_hourly_timeline(conn, start_timestamp, end_timestamp)
            
            # Top productive activities
            productive_activities = self._get_productive_activities(conn, start_timestamp, end_timestamp)
            
            return {
                "total_tracked_minutes": total_minutes,
                "by_category": by_category,
                "by_app": by_app,
                "timeline": timeline,
                "productive_activities": productive_activities,
                "excluded_minutes": 0  # TODO: track excluded time
            }
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get activity summary: {e}") from e
    
    def _get_hourly_timeline(self, conn, start_timestamp: int, end_timestamp: int) -> List[Dict[str, Any]]:
        """Get hourly breakdown of activity for timeline visualization."""
        try:
            # Convert timestamps to hours and get activity by hour
            cursor = conn.execute(
                """
                SELECT 
                    strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as hour,
                    category,
                    SUM(duration_seconds) as seconds
                FROM activity_log 
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY hour, category
                ORDER BY hour, seconds DESC
                """,
                (start_timestamp, end_timestamp)
            )
            
            timeline = []
            current_hour = None
            hour_data = None
            
            for row in cursor:
                hour = int(row[0])
                category = row[1]
                minutes = row[2] // 60
                
                if hour != current_hour:
                    if hour_data:
                        timeline.append(hour_data)
                    
                    hour_data = {
                        "hour": hour,
                        "total_minutes": 0,
                        "primary_category": category,
                        "categories": {}
                    }
                    current_hour = hour
                
                hour_data["categories"][category] = minutes
                hour_data["total_minutes"] += minutes
                
                # Update primary category if this one has more time
                if minutes > hour_data["categories"].get(hour_data["primary_category"], 0):
                    hour_data["primary_category"] = category
            
            if hour_data:
                timeline.append(hour_data)
            
            return timeline
            
        except sqlite3.Error:
            return []
    
    def _get_productive_activities(self, conn, start_timestamp: int, end_timestamp: int) -> List[Dict[str, Any]]:
        """Get most productive activities (deep work sessions)."""
        try:
            cursor = conn.execute(
                """
                SELECT 
                    app_name,
                    window_title,
                    category,
                    SUM(duration_seconds) as total_seconds,
                    COUNT(*) as session_count
                FROM activity_log 
                WHERE timestamp >= ? AND timestamp <= ? 
                    AND category IN ('deep_work', 'research')
                    AND app_name IS NOT NULL
                GROUP BY app_name, CASE 
                    WHEN window_title LIKE '%-%' 
                    THEN substr(window_title, 1, instr(window_title, '-') - 1)
                    ELSE window_title 
                END
                HAVING total_seconds >= 300  -- At least 5 minutes
                ORDER BY total_seconds DESC
                LIMIT 10
                """,
                (start_timestamp, end_timestamp)
            )
            
            productive_activities = []
            for row in cursor:
                productive_activities.append({
                    "app": row[0],
                    "context": row[1][:50] + "..." if len(row[1]) > 50 else row[1],
                    "category": row[2],
                    "minutes": row[3] // 60,
                    "sessions": row[4]
                })
            
            return productive_activities
            
        except sqlite3.Error:
            return []
    
    def insert_digest(self, digest: DigestEntry) -> int:
        """Insert digest entry into database.
        
        Args:
            digest: DigestEntry to insert
            
        Returns:
            ID of inserted row
        """
        try:
            with self.transaction() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO digests (
                        generated_at, period_start, period_end,
                        period_type, persona, content, token_usage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        digest.generated_at,
                        digest.period_start,
                        digest.period_end,
                        digest.period_type,
                        digest.persona,
                        digest.content,
                        digest.to_dict()['token_usage']
                    )
                )
                return cursor.lastrowid
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to insert digest: {e}") from e
    
    def get_latest_digest(self, period_type: str, persona: str) -> Optional[DigestEntry]:
        """Get the most recent digest for a period type and persona.
        
        Args:
            period_type: "day" or "week"
            persona: Coach persona name
            
        Returns:
            Latest DigestEntry or None
        """
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT * FROM digests 
                WHERE period_type = ? AND persona = ?
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (period_type, persona)
            )
            row = cursor.fetchone()
            
            return DigestEntry.from_dict(dict(row)) if row else None
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get latest digest: {e}") from e
    
    def cleanup_old_activities(self, older_than_timestamp: int) -> int:
        """Delete activity entries older than specified timestamp.
        
        Args:
            older_than_timestamp: Unix timestamp cutoff
            
        Returns:
            Number of deleted entries
        """
        try:
            with self.transaction() as conn:
                cursor = conn.execute(
                    "DELETE FROM activity_log WHERE timestamp < ?",
                    (older_than_timestamp,)
                )
                return cursor.rowcount
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to cleanup old activities: {e}") from e
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            conn = self._get_connection()
            
            # Get table sizes
            activity_count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
            digest_count = conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0]
            
            # Get file size
            file_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            
            # Get date range
            date_range = conn.execute(
                """
                SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts 
                FROM activity_log
                """
            ).fetchone()
            
            return {
                "activity_entries": activity_count,
                "digest_entries": digest_count,
                "file_size_bytes": file_size,
                "earliest_activity": date_range[0],
                "latest_activity": date_range[1],
            }
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get database stats: {e}") from e
    
    def close(self) -> None:
        """Close database connections."""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()


# Global database instance
_db_instance = None


def get_database(db_path: Optional[str] = None) -> Database:
    """Get global database instance.
    
    Args:
        db_path: Path to database file (only used for first initialization)
        
    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            raise ValueError("Database path required for first initialization")
        _db_instance = Database(db_path)
    return _db_instance