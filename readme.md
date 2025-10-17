# Orbit Agent

A modular browser automation agent platform built with LangGraph and Playwright.

## Project Structure

```
orbit-agent/
├── packages/
│   ├── orbit-core/        # Core library (agents, tools, clients)
│   ├── orbit-api/         # FastAPI service
│   └── orbit-browser/     # Playwright browser server
├── deployments/
│   └── docker/            # Docker compose and Dockerfiles
├── tests/                 # Test files
├── docs/                  # Documentation
└── benchmark/             # Performance benchmarks
```

## Packages

### orbit-core
Core library containing:
- Browser agent implementation (LangGraph)
- Browser automation utilities (Playwright)
- Clients (Redis, Supabase, LangGraph checkpointer/store)
- Configuration and logging utilities

See [packages/orbit-core/README.md](packages/orbit-core/README.md) for details.

### orbit-api
FastAPI service providing:
- RESTful API for threads, runs, and assistants
- Graph registry and LangGraph integration
- Authentication and storage via Supabase
- Redis caching

See [packages/orbit-api/README.md](packages/orbit-api/README.md) for details.

### orbit-browser
Standalone Playwright browser server:
- Persistent browser with WebSocket API
- Shared by multiple agent contexts
- Health monitoring

See [packages/orbit-browser/README.md](packages/orbit-browser/README.md) for details.

## Quick Start

### Prerequisites
- Python 3.13+
- Docker and Docker Compose
- Supabase account

### Setup

1. Clone the repository:
```bash
git clone <repo-url>
cd orbit-agent
```

2. Create `.env` file at project root:
```bash
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_key
REDIS_URL=redis://redis:6379
BROWSER_WSS_URL=ws://browser:3500
```

3. Start services with Docker Compose:
```bash
cd deployments/docker
docker compose --profile dev up
```

This will start:
- Redis (port 6379)
- Browser server (port 3500)
- API server (port 5000) with hot reload

### Development

#### Install packages locally:
```bash
# Install orbit-core
cd packages/orbit-core
pip install -e .

# Install orbit-api
cd ../orbit-api
pip install -e .

# Install orbit-browser
cd ../orbit-browser
pip install -e .
```

#### Run tests:
```bash
pytest tests/
```

## Architecture

The project follows a clean monorepo structure:

1. **orbit-core**: Pure library with no service dependencies
2. **orbit-api**: Service layer depending on orbit-core
3. **orbit-browser**: Standalone service with minimal dependencies

This separation ensures:
- Testable components
- Reusable core library
- Independent service deployment
- Clear dependency boundaries

See [docs/ARCHITECTURE_ANALYSIS.md](docs/ARCHITECTURE_ANALYSIS.md) for detailed analysis.

## Documentation

- [Architecture Analysis](docs/ARCHITECTURE_ANALYSIS.md)
- [Browser Updates Implementation](docs/BROWSER_UPDATES_FIX.md)
- [LangGraph API Documentation](docs/langgraph_api/)

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]

