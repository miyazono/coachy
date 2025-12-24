"""Priorities loading and parsing for coaching context."""
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Priorities:
    """Structured representation of user priorities."""
    weekly_priorities: List[str]
    daily_focus: List[str]
    standing_rules: List[str]
    success_criteria: List[str]
    raw_content: str
    
    def to_context_string(self) -> str:
        """Convert priorities to formatted string for LLM context."""
        context = []
        
        if self.weekly_priorities:
            context.append("## This Week's Priorities")
            for i, priority in enumerate(self.weekly_priorities, 1):
                context.append(f"{i}. {priority}")
            context.append("")
        
        if self.daily_focus:
            context.append("## Today's Focus")
            for focus in self.daily_focus:
                context.append(f"- {focus}")
            context.append("")
        
        if self.standing_rules:
            context.append("## Standing Rules")
            for rule in self.standing_rules:
                context.append(f"- {rule}")
            context.append("")
        
        if self.success_criteria:
            context.append("## Success Criteria")
            for criteria in self.success_criteria:
                context.append(f"- {criteria}")
        
        return "\n".join(context)


class PrioritiesLoader:
    """Loads and parses priorities from markdown files."""
    
    def __init__(self, priorities_file: str = "priorities.md"):
        """Initialize priorities loader.
        
        Args:
            priorities_file: Path to priorities markdown file
        """
        self.priorities_file = pathlib.Path(priorities_file)
    
    def load_priorities(self) -> Priorities:
        """Load priorities from markdown file.
        
        Returns:
            Priorities object with parsed content
        """
        if not self.priorities_file.exists():
            logger.warning(f"Priorities file not found: {self.priorities_file}")
            return Priorities(
                weekly_priorities=[],
                daily_focus=[],
                standing_rules=[],
                success_criteria=[],
                raw_content=""
            )
        
        try:
            with open(self.priorities_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return self._parse_priorities(content)
            
        except Exception as e:
            logger.error(f"Failed to load priorities: {e}")
            return Priorities(
                weekly_priorities=[],
                daily_focus=[],
                standing_rules=[],
                success_criteria=[],
                raw_content=""
            )
    
    def _parse_priorities(self, content: str) -> Priorities:
        """Parse priorities from markdown content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Parsed Priorities object
        """
        weekly_priorities = []
        daily_focus = []
        standing_rules = []
        success_criteria = []
        
        current_section = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                # Check for section headers
                if line.startswith('##'):
                    current_section = self._identify_section(line)
                continue
            
            # Parse list items based on current section
            if current_section:
                item = self._extract_list_item(line)
                if item:
                    if current_section == 'weekly':
                        weekly_priorities.append(item)
                    elif current_section == 'daily':
                        daily_focus.append(item)
                    elif current_section == 'standing':
                        standing_rules.append(item)
                    elif current_section == 'success':
                        success_criteria.append(item)
        
        return Priorities(
            weekly_priorities=weekly_priorities,
            daily_focus=daily_focus,
            standing_rules=standing_rules,
            success_criteria=success_criteria,
            raw_content=content
        )
    
    def _identify_section(self, header_line: str) -> Optional[str]:
        """Identify which section a header belongs to.
        
        Args:
            header_line: Markdown header line (## Section Name)
            
        Returns:
            Section identifier or None
        """
        header_text = header_line.lower()
        
        if any(keyword in header_text for keyword in ['week', 'weekly']):
            return 'weekly'
        elif any(keyword in header_text for keyword in ['today', 'daily', 'focus']):
            return 'daily'
        elif any(keyword in header_text for keyword in ['standing', 'rules', 'principles']):
            return 'standing'
        elif any(keyword in header_text for keyword in ['success', 'goals', 'outcomes']):
            return 'success'
        
        return None
    
    def _extract_list_item(self, line: str) -> Optional[str]:
        """Extract content from a markdown list item.
        
        Args:
            line: Line that might contain a list item
            
        Returns:
            Cleaned list item content or None
        """
        # Handle numbered lists (1. item, 2. item, etc.)
        numbered_match = re.match(r'^\d+\.\s*(.+)$', line)
        if numbered_match:
            return numbered_match.group(1).strip()
        
        # Handle bullet lists (- item, * item)
        bullet_match = re.match(r'^[-*]\s*(.+)$', line)
        if bullet_match:
            return bullet_match.group(1).strip()
        
        return None
    
    def update_priorities(self, priorities: Priorities) -> None:
        """Save updated priorities back to file.
        
        Args:
            priorities: Priorities object to save
        """
        try:
            # For now, just save the raw content back
            # In the future, could implement structured writing
            with open(self.priorities_file, 'w', encoding='utf-8') as f:
                f.write(priorities.raw_content)
            
            logger.info(f"Priorities updated: {self.priorities_file}")
            
        except Exception as e:
            logger.error(f"Failed to update priorities: {e}")


def load_priorities(priorities_file: str = "priorities.md") -> Priorities:
    """Convenience function to load priorities.
    
    Args:
        priorities_file: Path to priorities file
        
    Returns:
        Loaded Priorities object
    """
    loader = PrioritiesLoader(priorities_file)
    return loader.load_priorities()


def format_priorities_for_llm(priorities: Priorities) -> str:
    """Format priorities for LLM context with token efficiency.
    
    Args:
        priorities: Priorities object
        
    Returns:
        Formatted string for LLM context (~300-500 tokens)
    """
    if not any([priorities.weekly_priorities, priorities.daily_focus, 
                priorities.standing_rules, priorities.success_criteria]):
        return "No specific priorities provided."
    
    return priorities.to_context_string()


if __name__ == "__main__":
    # Test priorities loading
    print("Testing Priorities Loading")
    print("=" * 40)
    
    # Test with current priorities file
    priorities = load_priorities()
    
    print("Parsed Priorities:")
    print(f"Weekly: {len(priorities.weekly_priorities)} items")
    for i, item in enumerate(priorities.weekly_priorities, 1):
        print(f"  {i}. {item}")
    
    print(f"\nDaily: {len(priorities.daily_focus)} items")
    for item in priorities.daily_focus:
        print(f"  - {item}")
    
    print(f"\nStanding Rules: {len(priorities.standing_rules)} items")
    for item in priorities.standing_rules:
        print(f"  - {item}")
    
    print(f"\nSuccess Criteria: {len(priorities.success_criteria)} items")
    for item in priorities.success_criteria:
        print(f"  - {item}")
    
    print("\nFormatted for LLM:")
    print(format_priorities_for_llm(priorities))