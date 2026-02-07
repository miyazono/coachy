"""Coaching digest generation system."""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import pathlib

from ..config import get_config
from ..storage.db import get_database
from ..storage.models import DigestEntry
from .priorities import load_priorities, format_priorities_for_llm
from .llm import create_llm_client, LLMError, estimate_tokens
from .personas import load_persona_content, validate_persona_name, list_available_personas

logger = logging.getLogger(__name__)


class DigestError(Exception):
    """Exception raised when digest generation fails."""
    pass


class DigestGenerator:
    """Generates coaching digests using LLM analysis of activity data."""
    
    def __init__(self):
        """Initialize digest generator."""
        self.config = get_config()
        self.db = get_database(self.config.db_path)
        self.llm_client = None  # Lazy-loaded
        self._privacy_level_override = None
    
    def _get_llm_client(self):
        """Get LLM client, creating it if needed."""
        if self.llm_client is None:
            self.llm_client = create_llm_client()
        return self.llm_client
    
    def generate_digest(
        self,
        period: str = "day",
        persona: str = "grove",
        date: Optional[str] = None,
        privacy_level: Optional[str] = None
    ) -> str:
        """Generate a coaching digest for the specified period.

        Args:
            period: "day" or "week"
            persona: Coach persona name
            date: Specific date (YYYY-MM-DD) or None for most recent period
            privacy_level: Override config privacy level ("private" or "detailed")

        Returns:
            Generated digest text
        """
        self._privacy_level_override = privacy_level
        try:
            # Validate persona
            if not validate_persona_name(persona):
                available_personas = list_available_personas()
                raise DigestError(
                    f"Unknown persona '{persona}'. Available personas: {', '.join(available_personas)}"
                )
            
            # Get time range for analysis
            start_timestamp, end_timestamp = self._get_time_range(period, date)
            
            # Get activity data
            activity_summary = self.db.get_activity_summary(start_timestamp, end_timestamp)
            
            # Load priorities
            priorities = load_priorities()
            
            # Load persona using the persona manager
            persona_content = load_persona_content(persona)
            
            # Generate digest using LLM
            digest_content = self._generate_llm_digest(
                activity_summary, priorities, persona_content, period
            )
            
            # Store digest in database
            digest_entry = DigestEntry.create_now(
                period_start=start_timestamp,
                period_end=end_timestamp,
                period_type=period,
                persona=persona,
                content=digest_content,
                token_usage=getattr(self, '_last_token_usage', None)
            )
            
            self.db.insert_digest(digest_entry)
            
            logger.info(f"Generated {period} digest with {persona} persona")
            return digest_content
            
        except Exception as e:
            logger.error(f"Digest generation failed: {e}")
            raise DigestError(f"Failed to generate digest: {e}") from e
    
    def _get_time_range(self, period: str, date: Optional[str] = None) -> tuple[int, int]:
        """Get start and end timestamps for the specified period.
        
        Args:
            period: "day" or "week"
            date: Specific date or None for most recent
            
        Returns:
            Tuple of (start_timestamp, end_timestamp)
        """
        if date:
            if date == "yesterday":
                target_date = datetime.now() - timedelta(days=1)
            else:
                try:
                    target_date = datetime.strptime(date, "%Y-%m-%d")
                except ValueError:
                    raise DigestError(f"Invalid date format: {date}. Use YYYY-MM-DD or 'yesterday'")
        else:
            target_date = datetime.now()
        
        if period == "day":
            # Day: midnight to midnight
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)
            
            start_timestamp = int(start_of_day.timestamp())
            end_timestamp = int(end_of_day.timestamp())
            
        elif period == "week":
            # Week: Monday to Sunday
            days_since_monday = target_date.weekday()
            start_of_week = (target_date - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_of_week = start_of_week + timedelta(days=7)
            
            start_timestamp = int(start_of_week.timestamp())
            end_timestamp = int(end_of_week.timestamp())
            
        else:
            raise DigestError(f"Unsupported period: {period}")
        
        return start_timestamp, end_timestamp
    
    
    def _generate_llm_digest(
        self,
        activity_summary: Dict[str, Any],
        priorities: Any,
        persona_content: str,
        period: str
    ) -> str:
        """Generate digest using LLM.
        
        Args:
            activity_summary: Aggregated activity data
            priorities: Loaded priorities
            persona_content: Persona system prompt
            period: Period type ("day" or "week")
            
        Returns:
            Generated digest content
        """
        # Construct prompt
        prompt = self._construct_digest_prompt(
            activity_summary, priorities, persona_content, period
        )
        
        # Estimate tokens for budget tracking
        estimated_input_tokens = estimate_tokens(prompt)
        logger.debug(f"Digest prompt: ~{estimated_input_tokens} estimated input tokens")
        
        # Generate response
        try:
            llm_client = self._get_llm_client()
            response = llm_client.generate_text(
                prompt=prompt,
                max_tokens=1200,  # Keep output concise
                temperature=0.7
            )
            
            # Store token usage for later database insertion
            self._last_token_usage = response.get("usage", {})
            
            content = response.get("content", "")
            if not content:
                raise DigestError("Empty response from LLM")
            
            return content
            
        except LLMError as e:
            raise DigestError(f"LLM generation failed: {e}") from e
    
    def _construct_digest_prompt(
        self,
        activity_summary: Dict[str, Any],
        priorities: Any,
        persona_content: str,
        period: str
    ) -> str:
        """Construct the full prompt for digest generation.
        
        Args:
            activity_summary: Activity data
            priorities: User priorities
            persona_content: Persona system prompt
            period: Period type
            
        Returns:
            Complete prompt for LLM
        """
        # Format activity data for prompt with privacy level
        privacy_level = self._privacy_level_override or self.config.privacy_level
        activity_text = self._format_activity_for_prompt(activity_summary, privacy_level=privacy_level)
        
        # Format priorities
        priorities_text = format_priorities_for_llm(priorities)
        
        # Determine period description
        period_desc = "daily" if period == "day" else "weekly"
        
        prompt = f"""I need you to analyze my productivity data and provide coaching feedback.

{persona_content}

## My Current Priorities
{priorities_text}

## Activity Data for Analysis
{activity_text}

Please provide a {period_desc} coaching digest based on this data. Focus on:
1. How well my actual time allocation matched my stated priorities
2. Patterns in my activity that suggest strengths or areas for improvement
3. Specific, actionable recommendations for tomorrow (if daily) or next week (if weekly)
4. **Automation opportunities**: What repetitive tasks or patterns could/should be automated?
5. **Delegate to Claude**: What specific tasks from my activity could I have Claude Code or Claude do instead?
6. **Stop doing**: What activities should I eliminate or deprioritize entirely?
7. **System improvements**: How could this productivity tracking/coaching system itself be improved based on what you see?

Keep your response to 300-400 words. Be direct and specific in your coaching style as described above.

Respond in markdown format suitable for display in a terminal."""
        
        return prompt
    
    def _format_activity_for_prompt(
        self,
        activity_summary: Dict[str, Any],
        privacy_level: str = "private"
    ) -> str:
        """Format activity summary for inclusion in LLM prompt.

        Args:
            activity_summary: Activity data from database
            privacy_level: "private" (categories only) or "detailed" (full context)

        Returns:
            Formatted text for prompt
        """
        total_minutes = activity_summary.get("total_tracked_minutes", 0)

        if total_minutes == 0:
            return "No activity data available for this period."

        # Category breakdown — always included
        categories = activity_summary.get("by_category", {})
        category_text = []
        for category, data in sorted(categories.items(), key=lambda x: x[1]["minutes"], reverse=True):
            minutes = data["minutes"]
            percentage = data["percentage"]
            category_text.append(f"- {category}: {minutes} minutes ({percentage:.1f}%)")

        # Timeline — always included, but detail varies by privacy level
        timeline = activity_summary.get("timeline", [])
        if privacy_level == "private":
            active_hours = [
                f"{hour['hour']:02d}:00 ({hour['primary_category']}, {hour['total_minutes']}min)"
                for hour in timeline
                if hour["total_minutes"] >= 30
            ]
        else:
            active_hours = [
                f"{hour['hour']:02d}:00 ({hour['primary_category']}, {hour['total_minutes']}min)"
                for hour in timeline
                if hour["total_minutes"] >= 30
            ]

        result = f"""**Total Tracked Time:** {total_minutes} minutes ({total_minutes // 60}h {total_minutes % 60}m)

**Time by Category:**
{chr(10).join(category_text) if category_text else "No categorized activity"}"""

        # Detailed mode: include app names, window titles, productive sessions
        if privacy_level == "detailed":
            apps = activity_summary.get("by_app", {})
            app_text = []
            for app, data in sorted(apps.items(), key=lambda x: x[1]["minutes"], reverse=True)[:5]:
                minutes = data["minutes"]
                category = data["category"]
                app_text.append(f"- {app}: {minutes} minutes ({category})")

            productive = activity_summary.get("productive_activities", [])
            productive_text = []
            for activity in productive[:3]:
                app = activity["app"]
                context = activity["context"]
                minutes = activity["minutes"]
                productive_text.append(f"- {app} ({context}): {minutes} minutes")

            result += f"""

**Top Applications:**
{chr(10).join(app_text) if app_text else "No application data"}

**Most Productive Sessions:**
{chr(10).join(productive_text) if productive_text else "No significant productive sessions"}"""

        result += f"""

**Active Hours:**
{', '.join(active_hours) if active_hours else "No significant activity periods"}"""

        return result


def generate_digest(
    period: str = "day",
    persona: str = "grove",
    date: Optional[str] = None,
    privacy_level: Optional[str] = None
) -> str:
    """Convenience function to generate a digest.

    Args:
        period: "day" or "week"
        persona: Coach persona name
        date: Specific date or None
        privacy_level: Override config privacy level ("private" or "detailed")

    Returns:
        Generated digest content
    """
    generator = DigestGenerator()
    return generator.generate_digest(period, persona, date, privacy_level=privacy_level)


if __name__ == "__main__":
    # Test digest generation (requires API key)
    print("Testing Digest Generation")
    print("=" * 40)
    
    try:
        generator = DigestGenerator()
        
        # Test with fake activity data
        print("🧪 Testing digest generation...")
        
        # This would normally use real activity data from the database
        digest = generator.generate_digest(period="day", persona="grove")
        
        print("✅ Digest generated successfully!")
        print("\n" + "=" * 40)
        print(digest)
        print("=" * 40)
        
    except DigestError as e:
        print(f"❌ Digest generation failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()