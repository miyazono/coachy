"""LLM client abstraction for coaching digest generation."""
import logging
import os
from typing import Dict, Any, Optional

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from ..config import get_config

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Exception raised when LLM operations fail."""
    pass


class LLMClient:
    """Abstract base class for LLM clients."""
    
    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Generate text from prompt.
        
        Args:
            prompt: Input prompt for text generation
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)
            
        Returns:
            Dictionary with 'content' and 'usage' keys
        """
        raise NotImplementedError


class AnthropicClient(LLMClient):
    """Anthropic Claude API client."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        """Initialize Anthropic client.
        
        Args:
            api_key: Anthropic API key (if None, loads from environment)
            model: Model name to use
        """
        if not ANTHROPIC_AVAILABLE:
            raise LLMError("Anthropic library not available. Install with: pip install anthropic")
        
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter"
            )
        
        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Generate text using Anthropic Claude API.
        
        Args:
            prompt: Input prompt for text generation
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Dictionary with response content and usage info
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract content from response
            content = ""
            if response.content and len(response.content) > 0:
                content = response.content[0].text
            
            # Extract usage information
            usage = {
                "input_tokens": response.usage.input_tokens if response.usage else 0,
                "output_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": (
                    (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
                    if response.usage else 0
                )
            }
            
            logger.debug(
                f"Anthropic API call completed: "
                f"input={usage['input_tokens']}, output={usage['output_tokens']} tokens"
            )
            
            return {
                "content": content,
                "usage": usage
            }
            
        except anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}") from e
        except Exception as e:
            raise LLMError(f"Anthropic API call failed: {e}") from e


class LocalLLMClient(LLMClient):
    """Local LLM client for LM Studio, Ollama, MLX-LM, etc."""
    
    def __init__(self, endpoint: str, model: str):
        """Initialize local LLM client.
        
        Args:
            endpoint: Local LLM endpoint URL
            model: Model name
        """
        self.endpoint = endpoint
        self.model = model
        
        try:
            import openai
            self.client = openai.OpenAI(
                base_url=endpoint,
                api_key="not-needed"  # Local servers often don't need real API keys
            )
        except ImportError:
            raise LLMError("OpenAI library not available for local LLM. Install with: pip install openai")
    
    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Generate text using local LLM.
        
        Args:
            prompt: Input prompt for text generation
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Dictionary with response content and usage info
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            content = ""
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content or ""
            
            # Local LLMs often don't provide detailed usage stats
            usage = {
                "input_tokens": getattr(response.usage, 'prompt_tokens', 0) if response.usage else 0,
                "output_tokens": getattr(response.usage, 'completion_tokens', 0) if response.usage else 0,
                "total_tokens": getattr(response.usage, 'total_tokens', 0) if response.usage else 0
            }
            
            logger.debug(f"Local LLM call completed: {usage['total_tokens']} tokens")
            
            return {
                "content": content,
                "usage": usage
            }
            
        except (ConnectionError, TimeoutError) as e:
            raise LLMError(f"Local LLM connection failed: {e}") from e
        except Exception as e:
            raise LLMError(f"Local LLM call failed: {e}") from e


class MLXClient(LLMClient):
    """MLX-LM client for Apple Silicon optimized local inference."""
    
    def __init__(self, model_path: str, max_tokens: int = 1500):
        """Initialize MLX client.
        
        Args:
            model_path: Path to MLX model directory
            max_tokens: Maximum tokens to generate
        """
        self.model_path = model_path
        self.max_tokens = max_tokens
        
        try:
            import mlx_lm
            self.mlx_lm = mlx_lm
            # Test that model exists and loads
            self._test_model()
        except ImportError:
            raise LLMError("MLX-LM not available. Install with: pip install mlx-lm")
        except Exception as e:
            raise LLMError(f"Failed to load MLX model from {model_path}: {e}")
    
    def _test_model(self):
        """Test that the model can be loaded."""
        try:
            # Try to load model metadata to verify it exists
            import os
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model path does not exist: {self.model_path}")
            
            # Check for essential model files
            config_file = os.path.join(self.model_path, "config.json")
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"Model config not found: {config_file}")
                
        except Exception as e:
            raise LLMError(f"MLX model validation failed: {e}")
    
    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Generate text using MLX-LM.
        
        Args:
            prompt: Input prompt for text generation
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Dictionary with response content and usage info
        """
        try:
            # Use mlx_lm.generate for direct generation
            response = self.mlx_lm.generate(
                model=self.model_path,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # MLX-LM returns a generator, get the response
            if hasattr(response, '__iter__'):
                content = "".join(response)
            else:
                content = str(response)
            
            # Estimate token usage (MLX-LM doesn't provide detailed usage stats)
            estimated_input_tokens = estimate_tokens(prompt)
            estimated_output_tokens = estimate_tokens(content)
            
            usage = {
                "input_tokens": estimated_input_tokens,
                "output_tokens": estimated_output_tokens,
                "total_tokens": estimated_input_tokens + estimated_output_tokens
            }
            
            logger.debug(f"MLX-LM generation completed: {usage['total_tokens']} estimated tokens")
            
            return {
                "content": content,
                "usage": usage
            }
            
        except Exception as e:
            raise LLMError(f"MLX-LM generation failed: {e}") from e


def create_llm_client(config: Optional[Dict[str, Any]] = None) -> LLMClient:
    """Create appropriate LLM client based on configuration.
    
    Args:
        config: Configuration dictionary (if None, loads from global config)
        
    Returns:
        Configured LLM client
    """
    if config is None:
        app_config = get_config()
        config = {
            "provider": app_config.get("coach.llm_provider", "anthropic"),
            "anthropic_model": app_config.get("coach.anthropic.model", "claude-sonnet-4-20250514"),
            "local_endpoint": app_config.get("coach.local_llm.endpoint", "http://localhost:8080/v1"),
            "local_model": app_config.get("coach.local_llm.model", "gpt-oss-20b"),
            "mlx_model_path": app_config.get("coach.mlx.model_path"),
        }
    
    provider = config.get("provider", "anthropic")
    
    if provider == "anthropic":
        return AnthropicClient(
            model=config.get("anthropic_model", "claude-sonnet-4-20250514")
        )
    elif provider == "local":
        return LocalLLMClient(
            endpoint=config.get("local_endpoint", "http://localhost:8080/v1"),
            model=config.get("local_model", "gpt-oss-20b")
        )
    elif provider == "mlx":
        model_path = config.get("mlx_model_path")
        if not model_path:
            raise LLMError("MLX model_path not configured. Set coach.mlx.model_path in config.yaml")
        return MLXClient(model_path=model_path)
    else:
        raise LLMError(f"Unknown LLM provider: {provider}")


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string.
    
    Rough approximation: 1 token ≈ 4 characters for English text.
    
    Args:
        text: Text to estimate tokens for
        
    Returns:
        Estimated token count
    """
    return len(text) // 4


def test_llm_client(provider: str = "anthropic") -> bool:
    """Test LLM client functionality.
    
    Args:
        provider: LLM provider to test
        
    Returns:
        True if test passes, False otherwise
    """
    try:
        if provider == "anthropic":
            # Check if API key is available
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                print("❌ ANTHROPIC_API_KEY not set")
                return False
            
            client = AnthropicClient()
        elif provider == "local":
            client = LocalLLMClient(
                endpoint="http://localhost:8080/v1",
                model="gpt-oss-20b"
            )
        elif provider == "mlx":
            app_config = get_config()
            mlx_path = app_config.get("coach.mlx.model_path")
            if not mlx_path:
                print("MLX model_path not configured in config.yaml")
                return False
            client = MLXClient(model_path=mlx_path)
        else:
            print(f"❌ Unknown provider: {provider}")
            return False
        
        # Test simple generation
        response = client.generate_text(
            prompt="Say 'Hello, Coachy!' and nothing else.",
            max_tokens=50,
            temperature=0.1
        )
        
        content = response.get("content", "")
        usage = response.get("usage", {})
        
        print(f"✅ {provider.title()} client working")
        print(f"   Response: {content[:50]}...")
        print(f"   Tokens: {usage.get('total_tokens', 'unknown')}")
        
        return True
        
    except LLMError as e:
        print(f"❌ {provider.title()} client failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing {provider}: {e}")
        return False


if __name__ == "__main__":
    print("LLM Client Test")
    print("=" * 30)
    
    # Test Anthropic client
    print("\n🧪 Testing Anthropic client...")
    anthropic_works = test_llm_client("anthropic")
    
    # Test local LLM client (will likely fail unless running locally)
    print("\n🧪 Testing Local LLM client...")
    local_works = test_llm_client("local")
    
    if anthropic_works:
        print("\n✅ Ready for digest generation with Anthropic!")
    elif local_works:
        print("\n✅ Ready for digest generation with local LLM!")
    else:
        print("\n❌ No working LLM client found.")
        print("   Set ANTHROPIC_API_KEY environment variable to use Anthropic Claude.")