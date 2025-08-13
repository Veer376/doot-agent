# Orbit Agent - Project Structure

## Project Directory Structure

```
browser_agent/
├─ agent/
│  ├─ agent.py
│
├─ strategies/
│  ├─ tool_selection/
│  │  ├─ tool_selection_strategy.py  # get_active_tools, selection policies, filters
│  │  └── filters/
│  │        ├── __init__.py
│  │        ├── common_filters.py   # Predefined reusable `is_active` functions for context filtering
│  ├─ prompt_injection/
│  │  ├─ __init__.py
│  │  ├─ prompt_injection_strategy.py
│  │  └─ injections_registry.py
│  ├─ persona/
│  │  ├─ persona_manager.py          # PersonaManager (get, get_for_task, LLM-specific)
│  │  └─ personas/
│  │     ├─ executor.py
│  │     ├─ planner.py
│  │     ├─ reflection.py
│  │     └─ linkedin.py
│  └─ error_handling/
│  │  └─ error_strategy.py
│  └─ cost_control_strategy.py
│
├─ message_builder/
│  ├─ builder.py                     # builds MessageBlueprint only (no LLM calls)
│  ├─ blueprint.py                   # MessageBlueprint dataclass / schema
│  └─ formatter.py                   # LLM-specific message formatting helpers
│
├─ llm/
│  ├─ llm_manager.py
│  ├─ adapters/
│  │  ├─ __init__.py
│  │  ├─ gemini_adapter.py
│  │  ├─ langgraph_adapter.py
│  │  └─ openai_adapter.py
│  └─ config.py                      # timeouts, retry policies, token limits
│
├─ tools/
│── tools.py                 # Tool implementations (actual callable functions)
│── registry.py              # ToolRegistry with `register` decorator & storage
│
├─ perception/
│  ├─ __init__.py
│  ├─ dom_serializer.py              # DOM -> compact representation
│  ├─ screenshot_processor.py        # OCR / visual features / embeddings
│  └─ markdown_renderer.py
```

## Architecture Overview

### Current vs New Architecture

**Current Structure Issues:**

- Mixed concerns with intertwined logic for tools, messages, and personas
- Limited extensibility when adding new LLMs or strategies
- Implicit dependencies creating complex flows
- Testing challenges due to tight coupling

**New Architecture Benefits:**

- Clear separation of concerns with focused modules
- Strategy pattern for interchangeable components
- Pluggable design with adapters for different LLMs
- Independent component evolution
- Improved testability through isolation
- Better developer experience with clear organization

## Key Components

**1. Agent** - Central orchestrator managing state and execution flow

- Executes reasoning steps with LLMs
- Maintains agent and browser state
- Coordinates all module interactions

**2. Strategies** - Modular decision-making components

- Tool Selection: Context-aware tool filtering
- Prompt Injection: Dynamic prompt enhancement
- Persona Management: Task-specific agent behavior
- Error Handling: Standardized recovery mechanisms
- Cost Control: Token usage optimization

**3. Message Builder** - Constructs LLM messages

- Separates data structure (Blueprint) from construction logic
- Clean formatter adapters for different LLM providers

**4. LLM Integration** - Abstracts LLM interactions

- Provider-agnostic adapter pattern
- Centralized configuration management

**5. Tools** - Browser manipulation actions

- Registry-based tool discovery
- Decorators for automatic registration

**6. Perception** - Browser state representation

- Token-efficient DOM transformation
- Multiple representation strategies
