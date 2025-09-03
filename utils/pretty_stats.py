"""
Utility module for pretty-printing LLM usage statistics.
"""

from typing import Dict, Any
from tabulate import tabulate
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init()


def format_llm_stats(stats: Dict[str, Any]) -> str:
    """
    Format LLM usage statistics into a beautiful tabular display.

    Args:
        stats: Dictionary containing LLM usage statistics

    Returns:
        Formatted string with tables displaying the statistics
    """
    if not stats:
        return "No statistics available"

    # Initialize result
    result = []

    # Header
    result.append(f"{Fore.CYAN}{Style.BRIGHT}LLM USAGE STATISTICS{Style.RESET_ALL}")
    result.append("")

    # Model usage
    if "calls_by_model" in stats:
        model_data = []
        for model, calls in stats["calls_by_model"].items():
            model_data.append([model, calls])

        result.append(f"{Fore.GREEN}{Style.BRIGHT}MODEL USAGE:{Style.RESET_ALL}")
        result.append(
            tabulate(model_data, headers=["Model", "Calls"], tablefmt="pretty")
        )
        result.append("")

    # Token usage
    token_data = []
    token_fields = {
        "input_tokens": "Input Tokens",
        "output_tokens": "Output Tokens",
        "thought_tokens": "Thought Tokens",
        "tool_tokens": "Tool Tokens",
        "total_tokens": "Total Tokens",
    }

    for key, label in token_fields.items():
        if key in stats:
            # Handle nested dictionaries (like input_tokens)
            if isinstance(stats[key], dict):
                total = sum(stats[key].values())
                details = ", ".join(f"{k}: {v}" for k, v in stats[key].items())
                token_data.append([label, f"{total} ({details})"])
            else:
                token_data.append([label, stats[key]])

    result.append(f"{Fore.GREEN}{Style.BRIGHT}TOKEN USAGE:{Style.RESET_ALL}")
    result.append(tabulate(token_data, headers=["Type", "Count"], tablefmt="pretty"))
    result.append("")

    # Cost information
    cost_data = []
    cost_fields = {
        "input_cost_inr": "Input Cost (₹)",
        "output_cost_inr": "Output Cost (₹)",
        "total_cost_inr": "Total Cost (₹)",
        "total_cost_usd": "Total Cost ($)",
    }

    for key, label in cost_fields.items():
        if key in stats:
            cost_data.append([label, f"{stats[key]:.6f}"])

    result.append(f"{Fore.GREEN}{Style.BRIGHT}COST SUMMARY:{Style.RESET_ALL}")
    result.append(tabulate(cost_data, headers=["Metric", "Value"], tablefmt="pretty"))

    # Summary box
    summary = []
    summary.append(f"{Fore.YELLOW}{Style.BRIGHT}SUMMARY:{Style.RESET_ALL}")
    summary.append(f"Total API Calls: {stats.get('total_calls', 'N/A')}")
    summary.append(f"Total Tokens: {stats.get('total_tokens', 'N/A')}")
    summary.append(
        f"Total Cost: ₹{stats.get('total_cost_inr', 0):.6f} (${stats.get('total_cost_usd', 0):.6f})"
    )

    # Create a box around the summary
    max_length = max(
        len(line) - len(Fore.YELLOW + Style.BRIGHT + Style.RESET_ALL)
        for line in summary
    )
    separator = f"+" + "-" * (max_length + 2) + "+"

    result.append("")
    result.append(separator)
    for line in summary:
        padding = max_length - (
            len(line) - len(Fore.YELLOW + Style.BRIGHT + Style.RESET_ALL)
        )
        result.append(f"| {line}{' ' * padding} |")
    result.append(separator)

    return "\n".join(result)


def pretty_stats(stats: Dict[str, Any]) -> None:
    """
    Print LLM usage statistics in a beautiful format.

    Args:
        stats: Dictionary containing LLM usage statistics
    """
    print("\n" + "=" * 60)
    print(format_llm_stats(stats))
    print("=" * 60 + "\n")


if __name__=="__main__":
    """
    Test function to demonstrate the pretty print utility.

    Args:
        stats: Dictionary containing LLM usage statistics
    """
    pretty_stats(
        stats={
            "calls_by_model": {"gpt-3.5-turbo": 150, "gpt-4": 75},
            "input_tokens": {"gpt-3.5-turbo": 5000, "gpt-4": 3000},
            "output_tokens": {"gpt-3.5-turbo": 2000, "gpt-4": 1500},
            "thought_tokens": {"gpt-3.5-turbo": 1000, "gpt-4": 800},
            "tool_tokens": {"gpt-3.5-turbo": 500, "gpt-4": 400},
            "total_tokens": 12000,
            "input_cost_inr": 50.0,
            "output_cost_inr": 30.0,
            "total_cost_inr": 80.0,
            "total_cost_usd": 1.00,
            "total_calls": 225,
        }
    )
