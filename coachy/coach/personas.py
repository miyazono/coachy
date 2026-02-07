"""Coach persona management and loading system."""
import logging
import pathlib
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Persona:
    """Represents a coaching persona."""
    
    def __init__(self, name: str, content: str, description: str = ""):
        """Initialize persona.
        
        Args:
            name: Persona identifier (e.g., "grove", "huang")
            content: Full persona content/prompt
            description: Brief description of the persona
        """
        self.name = name
        self.content = content
        self.description = description
    
    def get_system_prompt(self) -> str:
        """Get the full system prompt for this persona."""
        return self.content
    
    def get_summary(self) -> str:
        """Get a brief summary of this persona."""
        if self.description:
            return self.description
        
        # Extract description from content if not provided
        lines = self.content.split('\n')
        for line in lines:
            if line.startswith('#') and '—' in line:
                # Extract from title line like "# Andy Grove — High Output Management Coach"
                return line.split('—', 1)[1].strip()
        
        return f"{self.name.title()} coaching persona"


class PersonaManager:
    """Manages loading and access to coaching personas."""
    
    def __init__(self, personas_dir: str = "personas"):
        """Initialize persona manager.

        Args:
            personas_dir: Directory containing persona markdown files
        """
        self.personas_dir = pathlib.Path(personas_dir)
        self.private_personas_dir = self.personas_dir.parent / "private-personas"
        self._personas = {}
        self._load_all_personas()
    
    def _load_all_personas(self) -> None:
        """Load all persona files from personas and private-personas directories."""
        dirs = [self.personas_dir, self.private_personas_dir]
        for d in dirs:
            if not d.exists():
                continue
            self._load_personas_from_dir(d)

    def _load_personas_from_dir(self, directory: pathlib.Path) -> None:
        """Load persona files from a single directory."""
        for persona_file in directory.glob("*.md"):
            persona_name = persona_file.stem
            try:
                with open(persona_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract description from first line if it's a title
                description = ""
                if content.startswith('#'):
                    first_line = content.split('\n')[0]
                    if '—' in first_line:
                        description = first_line.split('—', 1)[1].strip()
                
                persona = Persona(
                    name=persona_name,
                    content=content,
                    description=description
                )
                
                self._personas[persona_name] = persona
                logger.debug(f"Loaded persona: {persona_name}")
                
            except Exception as e:
                logger.warning(f"Failed to load persona {persona_name}: {e}")
    
    def get_persona(self, name: str) -> Optional[Persona]:
        """Get a persona by name.
        
        Args:
            name: Persona name (e.g., "grove", "huang")
            
        Returns:
            Persona object or None if not found
        """
        return self._personas.get(name.lower())
    
    def get_persona_content(self, name: str, default_content: str = None) -> str:
        """Get persona content for LLM system prompt.
        
        Args:
            name: Persona name
            default_content: Default content if persona not found
            
        Returns:
            Persona content for LLM prompt
        """
        persona = self.get_persona(name)
        if persona:
            return persona.get_system_prompt()
        
        if default_content is not None:
            return default_content
        
        logger.warning(f"Persona '{name}' not found, using default")
        return "You are a helpful productivity coach."
    
    def list_personas(self) -> List[str]:
        """Get list of available persona names.
        
        Returns:
            List of persona names
        """
        return list(self._personas.keys())
    
    def get_all_personas(self) -> Dict[str, Persona]:
        """Get all loaded personas.
        
        Returns:
            Dictionary mapping persona names to Persona objects
        """
        return self._personas.copy()
    
    def reload_personas(self) -> None:
        """Reload all personas from disk."""
        self._personas.clear()
        self._load_all_personas()
    
    def add_persona(self, name: str, content: str, description: str = "") -> None:
        """Add a persona programmatically.
        
        Args:
            name: Persona name
            content: Persona content/prompt
            description: Brief description
        """
        persona = Persona(name=name, content=content, description=description)
        self._personas[name.lower()] = persona
    
    def validate_persona(self, name: str) -> bool:
        """Check if a persona exists and is valid.
        
        Args:
            name: Persona name
            
        Returns:
            True if persona exists and has content
        """
        persona = self.get_persona(name)
        return persona is not None and bool(persona.content.strip())
    
    def get_persona_stats(self) -> Dict[str, any]:
        """Get statistics about loaded personas.
        
        Returns:
            Dictionary with persona statistics
        """
        total_personas = len(self._personas)
        total_content_chars = sum(len(p.content) for p in self._personas.values())
        avg_content_length = total_content_chars // total_personas if total_personas > 0 else 0
        
        return {
            "total_personas": total_personas,
            "persona_names": list(self._personas.keys()),
            "total_content_chars": total_content_chars,
            "avg_content_length": avg_content_length,
        }


# Global persona manager instance
_persona_manager = None


def get_persona_manager() -> PersonaManager:
    """Get the global persona manager instance.
    
    Returns:
        PersonaManager instance
    """
    global _persona_manager
    if _persona_manager is None:
        _persona_manager = PersonaManager()
    return _persona_manager


def list_available_personas() -> List[str]:
    """Get list of available persona names.
    
    Returns:
        List of persona names
    """
    return get_persona_manager().list_personas()


def load_persona_content(name: str, default: str = None) -> str:
    """Load persona content for LLM prompt.
    
    Args:
        name: Persona name
        default: Default content if persona not found
        
    Returns:
        Persona content
    """
    return get_persona_manager().get_persona_content(name, default)


def validate_persona_name(name: str) -> bool:
    """Validate that a persona name exists and is usable.
    
    Args:
        name: Persona name to validate
        
    Returns:
        True if persona is valid
    """
    return get_persona_manager().validate_persona(name)


if __name__ == "__main__":
    # Test persona management
    print("Persona Management Test")
    print("=" * 40)
    
    manager = PersonaManager()
    
    # List all personas
    personas = manager.list_personas()
    print(f"Available personas: {personas}")
    
    # Test each persona
    for persona_name in personas:
        persona = manager.get_persona(persona_name)
        if persona:
            print(f"\n📝 {persona_name.upper()}:")
            print(f"   Description: {persona.get_summary()}")
            print(f"   Content length: {len(persona.content)} chars")
            
            # Validate
            is_valid = manager.validate_persona(persona_name)
            print(f"   Valid: {'✓' if is_valid else '✗'}")
    
    # Show stats
    stats = manager.get_persona_stats()
    print(f"\n📊 Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Test loading specific persona content
    grove_content = load_persona_content("grove")
    print(f"\n🧪 Grove persona loaded: {len(grove_content)} chars")
    
    # Test invalid persona
    invalid_content = load_persona_content("nonexistent", "fallback content")
    print(f"🧪 Invalid persona fallback: {len(invalid_content)} chars")