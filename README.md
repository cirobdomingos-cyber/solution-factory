# Solution Factory

Multi-agent system that transforms a domain, idea, or problem statement into a complete solution blueprint — from market opportunity discovery through execution planning, with built-in critical review.

## The Problem

Going from "I have a vague idea" to "I have a validated, architected, actionable plan" normally requires weeks of research, multiple expert consultations, and significant cognitive overhead. Most ideas die not because they're bad, but because the path from idea to execution is unclear.

## What This Does

Feed it a domain or idea. Six specialized AI agents run a structured pipeline:

| Phase | Agent | What It Does |
|-------|-------|-------------|
| 1. Opportunity Discovery | Market Intelligence | Identifies pain points people will pay to solve |
| 2. Ideation | Product Strategist | Generates concrete product concepts with monetization |
| 3. Validation | Due Diligence Analyst | Stress-tests concepts, scores viability, kills weak ideas |
| 4. Architecture | Solution Architect | Designs roles (human + AI agents), tech stack, data flow |
| 5. Execution Planning | Engineering Manager | Creates phased roadmap with milestones and risk mitigations |
| 6. Critical Review | Chief Decision Officer | Final quality gate — go/no_go/conditional_go verdict |

The critic can send the pipeline back for rework (up to 2 iterations), creating a feedback loop that improves output quality.

## Architecture

```
User Prompt
    |
    v
[Orchestrator] --> Phase 1: Market Intel --> Phase 2: Ideation
                                                  |
    Phase 6: Critic <-- Phase 5: Execution <-- Phase 4: Architecture <-- Phase 3: Validation
         |
         |--- "go" --> Final Output
         |--- "no_go" --> Loop back to Phase 1 (with feedback)
```

**Design pattern**: Sequential pipeline with feedback loop. Each phase enriches a shared context dict that flows forward. The critic's feedback flows backward, triggering rework.

**Model strategy**: Opus for orchestration and critical review (high-stakes reasoning). Sonnet for specialist agents (throughput work).

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API key
cp .env.example .env
# Edit .env with your Anthropic API key
```

## Usage

```bash
# Single run
py -3.12 main.py "AI-powered invoice processing for small businesses"

# Interactive mode
py -3.12 main.py --interactive

# Streamlit app
py -3.12 -m streamlit run streamlit_app.py

# Verbose logging
py -3.12 main.py -v "developer productivity tools for remote teams"

# Custom output directory
py -3.12 main.py -o results/ "marketplace for freelance data analysts"
```

Results are exported as timestamped JSON files in the `output/` directory.

## Deploy on Railway

This project includes a `railway.toml` with a production start command for Streamlit.

### 1) Push to GitHub

Make sure this repository is in GitHub and includes:

- `requirements.txt`
- `streamlit_app.py`
- `railway.toml`
- `.python-version`

### 2) Create Railway project

1. In Railway, click **New Project**.
2. Choose **Deploy from GitHub repo**.
3. Select this repository.

Railway will auto-detect Python and install dependencies from `requirements.txt`.

### 3) Add environment variables

In Railway project variables, add:

- `ANTHROPIC_API_KEY` = your Anthropic API key
- `GOOGLE_CLIENT_ID` = OAuth client ID (for login)
- `GOOGLE_CLIENT_SECRET` = OAuth client secret
- `COOKIE_SECRET` = random 32+ char secret for auth cookies
- `DATABASE_URL` = Railway Postgres connection URL (recommended for persistent session history)

### 4) Deploy

Railway will use this start command from `railway.toml`:

- `python -m streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`

After deploy finishes, open the generated Railway URL.

### Notes

- Streamlit must bind to `0.0.0.0` and use Railway's `$PORT`.
- Keep secrets only in Railway Variables, never in Git.
- If your app cannot reach Anthropic, confirm `ANTHROPIC_API_KEY` exists in Railway.
- Session history uses Postgres automatically when `DATABASE_URL` or `SESSION_DATABASE_URL` is set.
- If no DB URL is configured, session history falls back to filesystem storage in `output/sessions/`.

## Stack

- **Python 3.12**
- **Anthropic SDK** — Claude Opus 4.6 (orchestrator/critic) + Claude Sonnet 4.6 (specialists)
- **Rich** — terminal UI with progress indicators
- **Pydantic** — data model validation
- **python-dotenv** — environment configuration

## Project Structure

```
solution-factory/
├── main.py                     # CLI entry point
├── orchestrator.py             # Master pipeline coordinator
├── config.py                   # Model and pipeline configuration
├── agents/
│   ├── base.py                 # Base agent class (Strategy pattern)
│   ├── market_intel.py         # Phase 1: Opportunity discovery
│   ├── ideator.py              # Phase 2: Solution concepts
│   ├── validator.py            # Phase 3: Concept stress-testing
│   ├── architect.py            # Phase 4: Roles, agents, tech design
│   ├── execution_planner.py    # Phase 5: Roadmap and milestones
│   └── critic.py               # Phase 6: Final quality gate
├── models/
│   └── solution.py             # Pipeline data models
└── utils/
    └── export.py               # JSON export utilities
```
