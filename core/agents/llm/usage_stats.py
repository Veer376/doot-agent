"""Global LLM usage statistics tracker."""

from .types import LLMUsageStats

# Global instance for tracking usage across all LLMs
global_usage_stats = LLMUsageStats()

def get_usage_stats() -> LLMUsageStats:
    """Get the global usage statistics instance."""
    return global_usage_stats

def reset_usage_stats():
    """Reset the global usage statistics."""
    global global_usage_stats
    global_usage_stats = LLMUsageStats()
