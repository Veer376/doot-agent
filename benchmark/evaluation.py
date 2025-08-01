#!/usr/bin/env python
"""
Browser-use benchmark evaluation script.

This script runs a set of predefined tasks against the browser agent and evaluates
performance metrics like success rate and task completion rate.
"""
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
import os
import sys
import re
import asyncio
import yaml
from typing import Dict, List
from datetime import datetime, timedelta

# Import project modules (matching structure from example.py)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from browser_use import Browser, BrowserConfig
from agents.browser_agent.agent import BrowserAgent

# --- CONFIGURATION ---
TASK_DIRECTORY = "benchmark/tasks"
RESULTS_DIRECTORY = "benchmark/results"

# --- DYNAMIC VALUE RESOLVER ---

# TODO: Also evaluate the time taken to complete each task.

def resolve_dynamic_values(value: str) -> str:
    """Resolves placeholders like [DATE_...] in task files."""
    if value == "[FIRST_DAY_OF_NEXT_MONTH]":
        today = datetime.now()
        # Find first day of next month
        if today.month == 12:
            first_day_next_month = datetime(today.year + 1, 1, 1)
        else:
            first_day_next_month = datetime(today.year, today.month + 1, 1)
        # Format: MM/DD/YYYY - adjust if your datepicker needs a different format
        return first_day_next_month.strftime("%m/%d/%Y")
    # Add other dynamic value resolvers here
    return value


# --- TASK LOADER ---


def load_tasks(task_directory: str) -> List[Dict]:
    """Loads all .yaml task files from a directory."""
    tasks = []
    if not os.path.exists(task_directory):
        print(f"Error: Task directory not found at '{task_directory}'")
        return []
    for filename in sorted(os.listdir(task_directory)):
        if filename.endswith(".yaml") and filename != "benchmark_metadata.yaml":
            with open(os.path.join(task_directory, filename), "r") as f:
                tasks.append(yaml.safe_load(f))
    return tasks


# --- AGENT ORCHESTRATOR ---
 
async def run_single_task(task: Dict):
    """Instantiates and runs the agent for a single task, returning all results."""
    print(f"\n--- Running Task: {task['task_id']} ---")
    print(f"Goal: {task['goal']}")

    # Configure browser using settings from example.py
    chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    config = BrowserConfig(browser_binary_path=chrome_path, headless=True)
    browser = Browser(config=config)
    browser_context = await browser.new_context()

    agent = BrowserAgent(
        session_id=task["task_id"],
        browser_context=browser_context,
        use_dom="normal",
        use_segmented_screenshot="normal",
    )

    try:
        
        final_state = await agent.run(task=task["goal"], prompt=f"go to the {task['start_url']} and complete the task")
        final_state['url'] = browser_context.state.url
        final_state['content'] = final_state['messages'][-1].content if final_state['messages'] else ""
        # final_state['history'] = [message.__dict__['action_type'] for message in final_state.get("messages", []) if isinstance(message, ToolMessage)]
        
    except Exception as e:
        print(f"  ERROR: Agent execution failed with an exception: {e}")
        return None
        
    finally:
        await browser.close()

    return final_state

# --- EVALUATION LOGIC ---


def _check_condition(state: Dict, condition: Dict) -> bool:
    """Evaluates a single condition against the final browser state."""
    if not state:
        return False

    condition_type = condition.get("type")
    page_content = state.get("content", "")
    page_url = state.get("url", "")

    if condition_type == "url_contains":
        return condition.get("substring", "") in page_url

    if condition_type == "string_exists":
        return condition.get("string", "") in page_content

    if condition_type == "element_text_equals":
        # This would need to be implemented with a DOM query
        print(f"  Warning: element_text_equals condition not implemented")
        return False

    if condition_type == "element_value_equals":
        # This would need to be implemented with a DOM query
        print(f"  Warning: element_value_equals condition not implemented")
        return False

    if condition_type == "element_not_exists":
        # This would need to be implemented with a DOM query
        print(f"  Warning: element_not_exists condition not implemented")
        return False

    if condition_type == "final_answer_contains":
        # Look for the string in the agent's final answer
        agent_messages = state.get("agent_messages", [])
        final_message = agent_messages[-1] if agent_messages else ""
        return condition.get("string", "") in final_message

    print(f"  Warning: Unknown condition type '{condition_type}'")
    return False


def evaluate_success(final_state: Dict, eval_config: Dict) -> bool:
    """Recursively evaluates the success conditions from the YAML file."""
    if not final_state or not eval_config:
        return False

    eval_type = eval_config.get("type")

    if eval_type == "and":
        return all(
            _check_condition(final_state, cond)
            for cond in eval_config.get("conditions", [])
        )
    elif eval_type == "or":
        return any(
            _check_condition(final_state, cond)
            for cond in eval_config.get("conditions", [])
        )
    else:
        return _check_condition(final_state, eval_config)


def calculate_completion_rate(action_history: list, golden_path: list) -> float:
    """Calculates TCR by comparing agent actions to the golden path using semantic matching."""
    if not golden_path:
        return 1.0

    common_prefix_length = 0
    for i, golden_action in enumerate(golden_path):
        if i >= len(action_history):
            break

        agent_action = action_history[i]

        # Semantic comparison - adapt this to match your tool naming convention
        is_match = True
        golden_action_type = golden_action.get("action")
        agent_action_type = agent_action.get("action")

        # Map golden_path actions to your tool.py names
        action_mapping = {
            "get_text": None,  # No direct equivalent
            "click_element": "click_element",
            "type_text": "type_text",
            "create_new_tab": "create_new_tab",
            "navigate_to_url": "navigate_to_url",
            "switch_to_tab": "switch_to_tab",
            "select_option": None,  # No direct equivalent
            "press_key": None,  # No direct equivalent
            "hover_element": None,  # No direct equivalent
            "accept_alert": None,  # No direct equivalent
            "drag_and_drop": None,  # No direct equivalent
        }

        # Check if the action types match after mapping
        mapped_golden_action = action_mapping.get(golden_action_type)
        if mapped_golden_action != agent_action_type:
            is_match = False

        # Check element parameters if applicable
        if is_match and "element" in golden_action and "element_index" in agent_action:
            # This is a simplified comparison - in reality, you'd need to
            # map between your element selectors and element indices
            is_match = True  # Simplified for now

        if is_match:
            common_prefix_length += 1
        else:
            break

    return common_prefix_length / len(golden_path)


# --- MAIN EXECUTION ---


async def main():
    """Main function to run the evaluation suite."""
    # 1. Get the run name from command-line arguments
    if len(sys.argv) > 1:
        run_name_raw = sys.argv[1]
    else:
        run_name_raw = "test"

    # Sanitize the run name to be a valid filename
    run_name = re.sub(r"[^a-zA-Z0-9_-]", "_", run_name_raw)

    # 2. Load benchmark tasks
    tasks = load_tasks(TASK_DIRECTORY)
    if not tasks:
        print("No tasks found. Exiting.")
        return

    # 3. Run all tasks and collect results
    results = []
    for task in tasks:
        task_result = await run_single_task(task)
        is_success = evaluate_success(task_result.get("final_state"), task.get("eval"))
        # completion_rate = calculate_completion_rate(
        #     task_result.get("action_history", []), task.get("golden_path", [])
        # )
        results.append(
            {
                "task_id": task["task_id"],
                "goal": task["goal"],
                "success": is_success,
                # "completion_rate": completion_rate,
                "token_usage": task_result.get("token_usage", {}),
            }
        )

    # 4. Calculate final metrics
    successful_tasks = [r for r in results if r["success"]]
    success_rate = (len(successful_tasks) / len(tasks)) * 100 if tasks else 0
    # avg_completion_rate = (
    #     (sum(r["completion_rate"] for r in results) / len(tasks)) * 100 if tasks else 0
    # )
    total_tokens = sum(r["token_usage"].get("total", 0) for r in results)
    avg_tokens = total_tokens / len(tasks) if tasks else 0

    # 5. Prepare the results report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = []
    report.append("=" * 80)
    report.append(f"ORBIT-AGENT EVALUATION REPORT")
    report.append(f"Run Name: {run_name_raw}")
    report.append(f"Timestamp: {timestamp}")
    report.append("=" * 80)
    report.append("\n--- SUMMARY ---")
    report.append(
        f"Success Rate (SR): {success_rate:.2f}% ({len(successful_tasks)}/{len(tasks)})"
    )
    # report.append(f"Avg. Task Completion Rate (TCR): {avg_completion_rate:.2f}%")
    report.append(f"Avg. Token Utilization: {avg_tokens:,.0f} tokens/task")
    report.append(f"Total Tokens Used: {total_tokens:,.0f}")
    report.append("\n--- DETAILED TASK RESULTS ---")

    for res in results:
        status = "✅ SUCCESS" if res["success"] else "❌ FAILURE"
        report.append("\n" + "-" * 40)
        report.append(f"Task ID: {res['task_id']}")
        report.append(f"Status: {status}")
        report.append(f"Completion Rate: {res['completion_rate']:.0%}")
        report.append(f"Tokens: {res['token_usage'].get('total', 0):,}")

    # 6. Save the report to a file
    os.makedirs(RESULTS_DIRECTORY, exist_ok=True)
    report_filename_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filepath = os.path.join(
        RESULTS_DIRECTORY, f"{run_name}_{report_filename_ts}.txt"
    )

    with open(report_filepath, "w") as f:
        f.write("\n".join(report))

    print("\n" + "=" * 80)
    print(f"Evaluation complete. Report saved to:\n{report_filepath}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
