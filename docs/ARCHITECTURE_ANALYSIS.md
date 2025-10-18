# Orbit Agent: Comprehensive Architecture Analysis & Restructuring Plan

**Date**: October 17, 2025  
**Status**: Analysis & Proposal (No Code Changes)  
**Author**: First-Principles Architecture Review

---

## Executive Summary

This document provides a thorough analysis of the current Orbit Agent project structure, identifies architectural flaws, and proposes a clean, standards-compliant restructuring aligned with Python packaging best practices, microservice patterns, and LangGraph deployment requirements.

**TL;DR**: The current architecture has grown organically and suffers from circular dependencies, unclear package boundaries, and complex deployment configuration. The proposed restructuring creates clean separation between core library code, agent implementations, and service deployments.

---

## Part 1: Current State Analysis

### 1.1 Directory Structure (As-Is)

```
orbit-agent/                          # Repository root
├── pyproject.toml                    # Root package definition (orbit-agent)
├── langgraph.json                    # LangGraph graph registry
├── .env                              # Root environment config
├── docker-compose.yaml               # Multi-service orchestration
│
├── core/                             # Core library package
│   ├── __init__.py
│   ├── default_assistants.py         # ❌ PROBLEM: Imports from services/
│   ├── chat_mode.py                  # Graph definition
│   ├── agents/
│   │   ├── browser_agent/
│   │   │   ├── agent.py              # Graph definition
│   │   │   ├── toolkit/
│   │   │   ├── perception/
│   │   │   └── ...
│   │   └── llm/
│   ├── browser_use/                  # Browser automation library
│   ├── clients/                      # Shared clients (Supabase, Redis, etc.)
│   │   ├── __init__.py
│   │   ├── supabase_client.py
│   │   ├── redis_client.py
│   │   ├── langgraph_checkpointer.py
│   │   └── langgraph_store.py
│   └── utils/
│
├── services/                         # Service implementations
│   ├── agent_platform/               # FastAPI service
│   │   ├── pyproject.toml            # Service package definition
│   │   ├── Dockerfile
│   │   ├── langgraph-platform.yaml   # ❌ UNUSED/REDUNDANT
│   │   └── app/
│   │       ├── __init__.py
│   │       ├── api/
│   │       │   ├── main.py           # FastAPI app (imports from core)
│   │       │   └── routes/
│   │       │       ├── assistants.py # ❌ Imports core.default_assistants
│   │       │       ├── threads.py
│   │       │       └── runs.py
│   │       ├── graph.py              # Graph registry loader
│   │       ├── schema.py             # Pydantic models
│   │       └── ...
│   │
│   └── browser/                      # Playwright server
│       ├── Dockerfile
│       └── server.py
│
├── tests/                            # Tests
└── benchmark/                        # Benchmarks
```

### 1.2 Package Boundaries (Current)

**Three packages exist:**

1. **`orbit-agent`** (root `pyproject.toml`)

   - Namespace: `core.*`
   - Purpose: Core library, agents, tools, clients
   - Dependencies: All agent deps (FastAPI, Playwright, LangChain, etc.)

2. **`agent-platform`** (`services/agent_platform/pyproject.toml`)

   - Namespace: `app.*`
   - Purpose: FastAPI REST API
   - Dependencies: Minimal (FastAPI, uvicorn, watchfiles)
   - **Runtime dependency**: Imports `core.*` via editable install

3. **Browser service** (no package, just Dockerfile)
   - Single `server.py` script
   - Purpose: Playwright WebSocket server

### 1.3 Import Dependency Graph

```
┌─────────────────────────────────────────────────────┐
│  services/agent_platform/app/                       │
│  ┌─────────────────────────────┐                   │
│  │ api/routes/assistants.py    │                   │
│  │                              │                   │
│  │ from core.default_assistants │──────────┐       │
│  │   import default_assistants  │          │       │
│  └─────────────────────────────┘          │       │
│                                             │       │
│  ┌─────────────────────────────┐          │       │
│  │ api/main.py                 │          │       │
│  │                              │          │       │
│  │ from core.utils.logging_config│        │       │
│  │ from core.clients import ... │         │       │
│  └─────────────────────────────┘          │       │
└──────────────────────────────────────────┼────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────┐
│  core/                                              │
│  ┌─────────────────────────────┐                   │
│  │ default_assistants.py       │                   │
│  │                              │                   │
│  │ from services.agent_platform │──────────────┐   │
│  │   .app.schema import Assistant│  ❌ CIRCULAR│   │
│  └─────────────────────────────┘              │   │
│                                                 │   │
│  ┌─────────────────────────────┐              │   │
│  │ agents/browser_agent/agent.py│             │   │
│  │                              │              │   │
│  │ from core.clients import ... │             │   │
│  │ from core.agents.llm import ...│           │   │
│  └─────────────────────────────┘              │   │
└────────────────────────────────────────────────┼───┘
                                                  │
                                                  │
                                    ┌─────────────┘
                                    │ ❌ ANTI-PATTERN
                                    ▼
```

---

## Part 2: Identified Problems

### 2.1 Circular Dependency (Critical)

**Evidence:**

- `core/default_assistants.py` imports `from services.agent_platform.app.schema import Assistant`
- `services/agent_platform/app/api/routes/assistants.py` imports `from core.default_assistants import default_assistants`

**Why it's problematic:**

- Creates tight coupling between library and service
- Makes it impossible to use `core` in other contexts without the service
- Violates the "acyclic dependencies principle"
- Fixed via hacky absolute import that bypasses Python's import system

**Impact**: Makes the `core` package non-reusable outside this specific deployment.

---

### 2.2 Unclear Package Ownership

**Problem**: `core/default_assistants.py` contains **application-level configuration**, not library code.

**Evidence:**

```python
# core/default_assistants.py
default_assistants = [
    {
        "assistant_id": "chat_mode",
        "name": "Chat Mode",
        "description": "A simple chat assistant...",
        ...
    },
    ...
]
```

**Why it's wrong:**

- Default assistants are **deployment configuration**, not core functionality
- Should live in the service layer (`services/agent_platform/app/config/`)
- `core` should only contain reusable library code (agents, tools, clients)

---

### 2.3 Fragmented Configuration Files

**Current state:**

- `langgraph.json` at repository root
- `langgraph-platform.yaml` in `services/agent_platform/` (unused)
- `.env` files in multiple locations

**Problems:**

- Docker mounts require manual mapping of config files
- Hard to understand which config applies where
- `langgraph.json` references code in `core/` but lives at root
- Environment variable `ORBIT_AGENT_ROOT=/orbit-agent` needed as workaround

---

### 2.4 Docker Mount Complexity

**Current Docker mounts (dev):**

```yaml
volumes:
  - ./services/agent_platform:/agent_platform
  - ./core:/orbit-agent/core
  - ./pyproject.toml:/orbit-agent/pyproject.toml:ro
  - ./langgraph.json:/orbit-agent/langgraph.json:ro # Added to fix path issues
```

**Problems:**

- Two separate install locations (`/orbit-agent` and `/agent_platform`)
- Requires `PYTHONPATH="/orbit-agent:/agent_platform"`
- Complex parent path traversal (`Path(__file__).resolve().parents[N]`)
- Fragile: breaks if directory nesting changes

---

### 2.5 Monolithic Dependency Tree

**Current `orbit-agent` package depends on:**

- FastAPI (only needed by service)
- Uvicorn (only needed by service)
- Playwright (only needed by browser service and browser_agent)
- LangChain (needed by agents)
- Supabase (needed by checkpointer)
- Redis (needed by clients)
- etc.

**Problems:**

- Installing `core` pulls in ALL dependencies, even if you only need one agent
- Impossible to use `core.agents.llm` without installing Playwright
- Violates "principle of least privilege" for dependencies

---

### 2.6 Schema Duplication Risk

**`services/agent_platform/app/schema.py`** defines:

```python
@dataclass
class Assistant:
    assistant_id: str
    config: Config
    graph_id: str
    ...
```

**But this is a domain model that:**

- Should be shared if `core` references it
- Currently causes circular import
- Will diverge if duplicated in both places

---

## Part 3: Industry Standards & Best Practices

### 3.1 Python Packaging Standards (PEP 517/518/621)

**Relevant PEPs:**

- **PEP 517/518**: Modern build system (pyproject.toml-based)
- **PEP 621**: Standard project metadata in pyproject.toml
- **PEP 420**: Implicit namespace packages

**Key principles:**

1. **One package = one pyproject.toml**
2. **Dependencies should flow one direction** (service → core, never core → service)
3. **Namespace packages** can share a common namespace (e.g., `orbit.core`, `orbit.api`)

---

### 3.2 Monorepo Patterns

**Industry examples:**

- Google (Bazel-based monorepo)
- Meta (Buck/Buck2)
- Python: Poetry workspaces, PDM multi-project, uv workspaces

**Best practices for Python monorepos:**

```
monorepo/
├── pyproject.toml              # Workspace root (optional)
├── packages/
│   ├── core/
│   │   └── pyproject.toml      # Independent package
│   ├── api/
│   │   └── pyproject.toml      # Depends on core
│   └── workers/
│       └── pyproject.toml      # Depends on core
└── deployments/
    └── docker-compose.yaml
```

**Dependency direction:**

```
api → core
workers → core
core → (external deps only)
```

---

### 3.3 LangGraph Deployment Patterns

**From LangGraph docs:**

1. **langgraph.json** should live at deployment root
2. **Graphs** should be importable Python modules
3. **Checkpointers/Stores** initialized at runtime via dependency injection

**Standard structure:**

```
app/
├── langgraph.json
├── graphs/
│   ├── chat_agent.py
│   └── browser_agent.py
└── api/
    └── main.py
```

---

### 3.4 Microservice Boundaries

**Clean separation:**

- **Library**: Reusable code (tools, agents, clients)
- **Service**: HTTP API, graph registry, routing
- **Deployment**: Docker, env config, orchestration

**Anti-patterns to avoid:**

- Service code in library
- Library importing from service
- Shared mutable state across boundaries

---

## Part 4: Target Architecture (Proposed)

### 4.1 High-Level Design Principles

1. **Strict acyclic dependencies**: `service → library`, never `library → service`
2. **Clear package boundaries**: Each package has one responsibility
3. **Minimal coupling**: Packages communicate via well-defined interfaces
4. **Configuration locality**: Config lives close to what uses it
5. **Deployment independence**: Each service can be deployed standalone

---

### 4.2 Proposed Directory Structure

```
orbit-agent/                          # Monorepo root
├── README.md
├── .gitignore
├── .env.example
│
├── packages/                         # 🆕 All Python packages here
│   │
│   ├── orbit-core/                   # 🔄 Renamed from 'core/'
│   │   ├── pyproject.toml            # Package: orbit-core
│   │   ├── README.md
│   │   └── orbit_core/               # Namespace: orbit_core.*
│   │       ├── __init__.py
│   │       ├── agents/               # Agent implementations
│   │       │   ├── browser_agent/
│   │       │   └── llm/
│   │       ├── browser_use/          # Browser automation toolkit
│   │       ├── clients/              # Shared infrastructure clients
│   │       │   ├── supabase.py
│   │       │   ├── redis.py
│   │       │   ├── checkpointer.py
│   │       │   └── store.py
│   │       ├── tools/                # Reusable tools
│   │       └── utils/                # Utilities
│   │
│   └── orbit-api/                    # 🔄 Renamed from 'services/agent_platform'
│       ├── pyproject.toml            # Package: orbit-api
│       ├── Dockerfile
│       ├── langgraph.json            # 🆕 Moved here (deployment config)
│       ├── README.md
│       └── orbit_api/                # Namespace: orbit_api.*
│           ├── __init__.py
│           ├── config/               # 🆕 Application configuration
│           │   ├── __init__.py
│           │   └── default_assistants.py  # 🆕 Moved from core/
│           ├── api/                  # FastAPI routes
│           │   ├── main.py
│           │   └── routes/
│           │       ├── assistants.py
│           │       ├── threads.py
│           │       └── runs.py
│           ├── graph/                # Graph registry & loading
│           │   ├── __init__.py
│           │   └── registry.py       # Renamed from graph.py
│           ├── models/               # 🆕 Domain models (shared schemas)
│           │   ├── __init__.py
│           │   └── assistant.py      # Assistant dataclass
│           └── utils/
│
├── services/                         # Non-Python services
│   └── browser/
│       ├── Dockerfile
│       └── server.py                 # Standalone Playwright server
│
├── deployments/                      # 🆕 Deployment configs
│   ├── docker/
│   │   ├── docker-compose.yaml       # 🆕 Moved from root
│   │   ├── docker-compose.dev.yaml   # Dev overrides
│   │   └── .env.example
│   └── kubernetes/                   # Future K8s manifests
│
├── tests/                            # Integration tests
└── docs/                             # Documentation
```

---

### 4.3 Package Dependency Graph (Target)

```
┌─────────────────────────────────┐
│  orbit-api                      │
│  (FastAPI service)              │
│                                  │
│  from orbit_core.agents import  │
│  from orbit_core.clients import │
│  from .config import defaults   │
└────────────┬────────────────────┘
             │ depends on
             ▼
┌─────────────────────────────────┐
│  orbit-core                     │
│  (Library package)              │
│                                  │
│  Pure library code:             │
│  - Agents                       │
│  - Tools                        │
│  - Clients                      │
│  - Browser automation           │
└─────────────────────────────────┘
             │ depends on
             ▼
┌─────────────────────────────────┐
│  External packages              │
│  (LangChain, Playwright, etc.)  │
└─────────────────────────────────┘
```

**✅ No circular dependencies**  
**✅ Clear separation of concerns**  
**✅ orbit-core is reusable**

---

### 4.4 Revised pyproject.toml Files

#### `packages/orbit-core/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "orbit-core"
version = "0.1.0"
description = "Core library for Orbit Agent: agents, tools, and infrastructure clients"
requires-python = ">=3.13"
dependencies = [
    # Core LangChain/LangGraph
    "langchain>=0.3.27",
    "langgraph>=0.6.4",
    "langgraph-checkpoint>=2.1.1",
    "langgraph-checkpoint-postgres>=2.0.23",

    # LLM providers
    "google-genai>=1.29.0",
    "langchain-google-genai>=2.1.9",

    # Infrastructure clients
    "supabase>=2.18.1",
    "redis>=6.4.0",
    "psycopg[binary]>=3.2.10",

    # Utilities
    "pydantic>=2.11.7",
    "httpx>=0.25.0",
    "pillow>=11.3.0",
    "structlog>=25.4.0",
]

[project.optional-dependencies]
# Browser agent optional dependency group
browser = [
    "playwright>=1.54.0",
    "pyautogui>=0.9.54",
    "readability-lxml>=0.8.4.1",
]

# Development dependencies
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["orbit_core*"]
```

#### `packages/orbit-api/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "orbit-api"
version = "0.1.0"
description = "FastAPI REST API for Orbit Agent platform"
requires-python = ">=3.13"
dependencies = [
    # Service dependencies
    "fastapi>=0.116.1",
    "uvicorn>=0.35.0",
    "watchfiles>=0.21.0",

    # Core library (local editable install in dev, package ref in prod)
    "orbit-core @ file:///${PROJECT_ROOT}/packages/orbit-core",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "httpx>=0.25.0",  # For testing FastAPI
]

[tool.setuptools.packages.find]
where = ["."]
include = ["orbit_api*"]
```

---

### 4.5 Revised Docker Setup

#### `packages/orbit-api/Dockerfile`

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install orbit-core first (better layer caching)
COPY packages/orbit-core /tmp/orbit-core
RUN pip install --no-cache-dir /tmp/orbit-core

# Copy and install orbit-api
COPY packages/orbit-api /app
RUN pip install --no-cache-dir /app

# Expose port
EXPOSE 5000

# Run the API service
CMD ["uvicorn", "orbit_api.api.main:app", "--host", "0.0.0.0", "--port", "5000"]
```

#### `deployments/docker/docker-compose.yaml`

```yaml
services:
  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping | grep PONG"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks:
      - orbit

  browser:
    build:
      context: ../../
      dockerfile: services/browser/Dockerfile
    environment:
      - PLAYWRIGHT_PORT=3500
    ports:
      - "3500:3500"
    shm_size: "1gb"
    healthcheck:
      test: ["CMD-SHELL", "test -s /var/run/playwright-ws-endpoint"]
      interval: 5s
      timeout: 5s
      retries: 30
    networks:
      - orbit

  api:
    build:
      context: ../../
      dockerfile: packages/orbit-api/Dockerfile
    depends_on:
      redis:
        condition: service_healthy
      browser:
        condition: service_healthy
    env_file:
      - .env
    environment:
      - REDIS_URL=redis://redis:6379
      - BROWSER_WSS_URL=ws://browser:3500
    ports:
      - "5000:5000"
    networks:
      - orbit

networks:
  orbit:
    driver: bridge
```

#### Development override (`deployments/docker/docker-compose.dev.yaml`)

```yaml
services:
  api:
    volumes:
      # Mount source code for hot reload
      - ../../packages/orbit-api/orbit_api:/app/orbit_api
      - ../../packages/orbit-core/orbit_core:/usr/local/lib/python3.13/site-packages/orbit_core
    command:
      [
        "uvicorn",
        "orbit_api.api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "5000",
        "--reload",
      ]
    environment:
      - WATCHFILES_FORCE_POLLING=true
```

**Usage:**

```bash
# Production
docker compose -f deployments/docker/docker-compose.yaml up

# Development
docker compose -f deployments/docker/docker-compose.yaml \
               -f deployments/docker/docker-compose.dev.yaml up
```

---

### 4.6 Import Pattern Changes

#### Before (problematic):

```python
# services/agent_platform/app/api/routes/assistants.py
from core.default_assistants import default_assistants  # ❌ Library importing config
from ...schema import Assistant  # ❌ Relative imports across packages
```

#### After (clean):

```python
# packages/orbit-api/orbit_api/api/routes/assistants.py
from orbit_api.config.default_assistants import default_assistants  # ✅ Local config
from orbit_api.models.assistant import Assistant  # ✅ Local domain model
from orbit_core.agents import browser_agent  # ✅ Library import
```

---

### 4.7 Configuration Management

#### Before:

- `langgraph.json` at repo root
- Hard-coded paths with `Path(__file__).parents[N]`
- Environment variable workarounds

#### After:

```python
# packages/orbit-api/orbit_api/graph/registry.py
from pathlib import Path

# Config file lives next to the service code
CONFIG_PATH = Path(__file__).parent.parent / "langgraph.json"

def load_graphs():
    """Load graphs from the service's langgraph.json"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"langgraph.json not found at {CONFIG_PATH}")

    # Load and register graphs...
```

**No path traversal, no environment variable hacks, just clean relative paths.**

---

## Part 5: Migration Plan

### Phase 1: Preparation (No Breaking Changes)

**Goal**: Set up new structure alongside old one.

1. **Create new directory structure**:

   ```bash
   mkdir -p packages/orbit-core/orbit_core
   mkdir -p packages/orbit-api/orbit_api
   mkdir -p deployments/docker
   ```

2. **Copy pyproject.toml templates** (from section 4.4)

3. **Create git branch**:
   ```bash
   git checkout -b refactor/clean-architecture
   ```

---

### Phase 2: Move Core Package

**Goal**: Relocate `core/` → `packages/orbit-core/orbit_core/`

1. **Move core code**:

   ```bash
   git mv core packages/orbit-core/orbit_core
   ```

2. **Update imports in core** (automated with tool):

   ```bash
   # Find/replace:
   from core. → from orbit_core.
   ```

3. **Create new pyproject.toml**:

   - Copy content from section 4.4
   - Place at `packages/orbit-core/pyproject.toml`

4. **Remove `core/default_assistants.py`** (will move to API service later)

5. **Test core package installation**:
   ```bash
   cd packages/orbit-core
   pip install -e .
   python -c "from orbit_core.agents import browser_agent; print('✓')"
   ```

---

### Phase 3: Move API Service

**Goal**: Relocate `services/agent_platform/` → `packages/orbit-api/`

1. **Move service code**:

   ```bash
   git mv services/agent_platform/app packages/orbit-api/orbit_api
   ```

2. **Create config module**:

   ```bash
   mkdir packages/orbit-api/orbit_api/config
   # Move default_assistants.py here
   ```

3. **Create models module**:

   ```bash
   mkdir packages/orbit-api/orbit_api/models
   # Move schema.py content here, rename to assistant.py
   ```

4. **Update imports in API** (automated):

   ```bash
   # Find/replace:
   from core. → from orbit_core.
   from app. → from orbit_api.
   ```

5. **Move langgraph.json**:

   ```bash
   mv langgraph.json packages/orbit-api/
   ```

6. **Update graph paths** in `langgraph.json`:
   ```json
   {
     "graphs": {
       "chat_mode": "orbit_core.chat_mode:graph",
       "browser_agent": "orbit_core.agents.browser_agent.agent:graph"
     }
   }
   ```

---

### Phase 4: Update Docker Configuration

1. **Create new Dockerfile**:

   - Use template from section 4.5
   - Place at `packages/orbit-api/Dockerfile`

2. **Move docker-compose.yaml**:

   ```bash
   mv docker-compose.yaml deployments/docker/
   ```

3. **Update docker-compose paths**:

   - `context: ../../`
   - `dockerfile: packages/orbit-api/Dockerfile`

4. **Create dev override**:

   - Use template from section 4.5
   - Place at `deployments/docker/docker-compose.dev.yaml`

5. **Test build**:
   ```bash
   cd deployments/docker
   docker compose build
   docker compose up
   ```

---

### Phase 5: Update Tests & Documentation

1. **Update test imports**:

   ```bash
   # Find/replace in tests/:
   from core. → from orbit_core.
   ```

2. **Update documentation**:

   - README.md (new structure diagram)
   - CONTRIBUTING.md (new dev setup)
   - ARCHITECTURE.md (this document)

3. **Create migration guide**:
   - For contributors
   - For deployments
   - For dependent projects

---

### Phase 6: Cleanup

1. **Remove old directories**:

   ```bash
   git rm -r core/
   git rm -r services/agent_platform/
   git rm docker-compose.yaml
   ```

2. **Update root pyproject.toml** (if keeping workspace root):

   ```toml
   [tool.workspace]
   members = ["packages/orbit-core", "packages/orbit-api"]
   ```

3. **Final verification**:
   - Run all tests
   - Build Docker images
   - Test API endpoints
   - Deploy to staging

---

## Part 6: Benefits of Target Architecture

### 6.1 Cleaner Dependencies

✅ **No circular dependencies**  
✅ **Clear dependency direction**: `orbit-api → orbit-core → external`  
✅ **Reduced coupling**: Services and library are independent

### 6.2 Improved Reusability

✅ **`orbit-core` can be pip-installed** in other projects  
✅ **Browser agent usable standalone** without API service  
✅ **Optional dependencies** (e.g., `orbit-core[browser]`)

### 6.3 Simplified Docker Builds

✅ **Single context** for multi-stage builds  
✅ **No complex mounts** in production  
✅ **Better layer caching**: core deps change less often

### 6.4 Easier Testing

✅ **Unit test each package independently**  
✅ **Integration tests in deployments/**  
✅ **Clear boundaries** reduce test complexity

### 6.5 Better Developer Experience

✅ **Clear package structure**: developers know where code belongs  
✅ **Simplified imports**: `from orbit_core.*` vs. `from core.*`  
✅ **Hot reload works reliably** with clean mounts

### 6.6 Future-Proof

✅ **Ready for multi-service expansion** (add `orbit-worker`, `orbit-scheduler`, etc.)  
✅ **Kubernetes-ready**: each package = container  
✅ **Monorepo tooling** compatible (Poetry workspaces, uv, etc.)

---

## Part 7: Risk Assessment & Mitigation

### Risk 1: Breaking Existing Imports

**Mitigation**:

- Use automated refactoring tools (`sed`, `ruff`, IDE refactoring)
- Implement in feature branch with comprehensive tests
- Create import compatibility shims during transition

### Risk 2: Docker Build Failures

**Mitigation**:

- Test each Dockerfile change incrementally
- Keep old compose file until new one verified
- Use multi-stage builds for rollback capability

### Risk 3: Deployment Disruption

**Mitigation**:

- Blue-green deployment strategy
- Keep old structure in separate branch
- Gradual rollout to staging → production

### Risk 4: Developer Onboarding Confusion

**Mitigation**:

- Update all documentation before merge
- Record video walkthrough of new structure
- Create migration guide for contributors

---

## Part 8: Alternative Architectures Considered

### Alternative 1: Keep Everything in `core/`

**Pros**: No file moves needed  
**Cons**: Doesn't solve circular dependency, unclear boundaries  
**Verdict**: ❌ Not recommended

### Alternative 2: Namespace Packages (`orbit.core`, `orbit.api`)

**Pros**: Shared namespace, follows PEP 420  
**Cons**: More complex imports, tooling compatibility issues  
**Verdict**: ⚠️ Possible but adds complexity

### Alternative 3: Full Microservices Split

**Pros**: Ultimate decoupling  
**Cons**: Operational overhead, network latency, data consistency challenges  
**Verdict**: ⏳ Future evolution, not needed now

---

## Part 9: Conclusion & Recommendation

### Summary

The current architecture has **grown organically** and suffers from:

1. Circular dependencies between library and service
2. Configuration scattered across multiple locations
3. Complex Docker mount configurations
4. Unclear package boundaries

### Recommendation

**Proceed with the proposed restructuring** (Part 4: Target Architecture).

**Rationale**:

- Aligns with Python packaging best practices
- Eliminates circular dependencies
- Simplifies Docker configuration
- Improves code reusability
- Sets foundation for future scaling

**Implementation timeline**: 2-3 days for migration, 1 week for full testing and documentation.

### Next Steps

1. **Review this document** with the team
2. **Get consensus** on target architecture
3. **Create detailed task breakdown** for migration
4. **Set up feature branch** and begin Phase 1
5. **Iterate and validate** at each phase

---

## Appendix A: Dependency Analysis

### Current Dependencies by Layer

**orbit-agent (core)**:

- 40+ dependencies (everything)
- Mix of library and service deps

**agent-platform (service)**:

- 3 explicit deps
- Implicit dependency on all of orbit-agent

### Target Dependencies by Layer

**orbit-core**:

- ~25 core library deps
- Optional dependency groups for specialized features

**orbit-api**:

- ~3 service deps
- 1 local dependency (`orbit-core`)

---

## Appendix B: File Move Checklist

- [ ] Move `core/` → `packages/orbit-core/orbit_core/`
- [ ] Move `services/agent_platform/app/` → `packages/orbit-api/orbit_api/`
- [ ] Move `core/default_assistants.py` → `packages/orbit-api/orbit_api/config/`
- [ ] Move `langgraph.json` → `packages/orbit-api/`
- [ ] Move `docker-compose.yaml` → `deployments/docker/`
- [ ] Create new Dockerfiles
- [ ] Update all imports (automated)
- [ ] Update tests
- [ ] Update documentation

---

**End of Analysis**

This document serves as a comprehensive blueprint for restructuring the Orbit Agent project. No code changes have been made—this is purely analysis and planning. Please review and provide feedback before proceeding with implementation.
