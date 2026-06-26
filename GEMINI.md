# Coding Agent Guide — Executive Diplomatic Co-Pilot

## Project Identity
- **Name:** Executive Diplomatic Co-Pilot
- **Track:** Agents for Business
- **Framework:** Google ADK 2.0 (Workflow API)
- **Model:** `gemini-2.5-flash` (do NOT change this)
- **Pattern:** Dual-agent + HITL Workflow + MCP stdio server + guardrail nodes

---

## Prerequisites

Install the CLI (one-time):
```bash
uv tool install google-agents-cli
```

---

## Development Phases

### Phase 1: Understand Requirements
Before writing any code, understand the project's requirements, constraints, and success criteria.

### Phase 2: Build and Implement
Implement agent logic in `app/`. Use `agents-cli playground` for interactive testing. Iterate based on user feedback.

### Phase 3: The Evaluation Loop (Main Iteration Phase)
Start with 1-2 eval cases, run `agents-cli eval generate`, then `agents-cli eval grade`, iterate by making changes and rerunning both commands until satisfied. Expect 5-10+ iterations. Once you have a baseline, reach for `agents-cli eval compare` (regression diffs), `agents-cli eval analyze` (cluster failure modes), and `agents-cli eval optimize` (auto-tune prompts). See the **Evaluation Guide** for metrics, dataset schema, LLM-as-judge config, and common gotchas.

### Phase 4: Pre-Deployment Tests
Run `uv run pytest tests/unit tests/integration`. Fix issues until all tests pass.

### Phase 5: Deploy to Dev
**Requires explicit human approval.** Run `agents-cli deploy` only after user confirms. See the **Deployment Guide** for details.

### Phase 6: Production Deployment
Ask the user: Option A (simple single-project) or Option B (full CI/CD pipeline with `agents-cli infra cicd`).

---

## Development Commands

| Command | Purpose |
|---------|---------|
| `agents-cli playground` | Interactive local testing |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests |
| `agents-cli eval dataset synthesize` | Synthesize multi-turn eval scenarios for your agent |
| `agents-cli eval generate` | Run agent on eval dataset, produce traces |
| `agents-cli eval grade` | Run agent evaluations on the traces |
| `agents-cli eval compare` | Compare two grade-results files (regression check) |
| `agents-cli eval analyze` | Cluster failure modes from grade results |
| `agents-cli eval metric list` | List built-in metrics available in the SDK |
| `agents-cli eval optimize` | Auto-tune agent prompts using eval data |
| `agents-cli lint` | Check code quality |
| `agents-cli infra single-project` | Set up project infrastructure (Terraform) |
| `agents-cli deploy` | Deploy to dev |
| `agents-cli scaffold enhance` | Add deployment target or CI/CD to project |
| `agents-cli scaffold upgrade` | Upgrade project to latest version |

---

## Project-Specific Architecture Notes

### Agents
- **`extraction_agent`** (`LlmAgent`): Takes raw mentor transcript text from session state (`mentor_text`), extracts tone/frameworks/vocabulary, outputs structured `PersonaSummary` to `ctx.state["persona_summary"]`. Uses MCP `summarize_persona` tool.
- **`execution_agent`** (`LlmAgent`): Sub-agent called by orchestrator via `AgentTool`. Generates the actual diplomatic advice in the mentor's voice.
- **`orchestrator`** (`LlmAgent`): Reads `{persona_summary}` and `{user_dilemma}` from state, calls MCP `validate_dilemma_type` and `generate_diplomatic_opener`, then delegates to `execution_agent`.

### Workflow Nodes
- **`onboard_user`** (`@node`): HITL — collects `profile_name` and `mentor_text` via `RequestInput`.
- **`get_dilemma`** (`@node`): HITL — shows persona summary, collects `user_dilemma` via `RequestInput`.
- **`security_checkpoint`** (`FunctionNode`): PII scrubbing → injection detection → compliance check → audit log → routes `"clear"` or `"security_violated"`.
- **`compliance_warning`** (`FunctionNode`): Terminal blocked-response node.
- **`format_output`** (`FunctionNode`): Wraps final advice with persona and compliance badge.
- **`final_node`** (`FunctionNode`): Pass-through terminal node.

### MCP Server (`app/mcp_server.py`)
Runs as a stdio subprocess. 4 tools:
- `summarize_persona(tone_traits, frameworks, vocabulary)` → compact embedding string
- `validate_dilemma_type(dilemma_text)` → JSON `{dilemma_category, recommended_framework}`
- `generate_diplomatic_opener(tone, dilemma_category)` → opening sentence string
- `check_compliance_flag(text)` → JSON `{is_compliant, reason, severity}`

### Security Guardrail Logic
The `_security_checkpoint_fn` function in `agent.py` implements:
1. Regex PII scrubbing (email, phone, 9–12 digit IDs)
2. Injection keyword detection (7 patterns, case-insensitive)
3. Compliance violation detection (8 terms, case-insensitive)
4. Route decision: `"clear"` → orchestrator, `"security_violated"` → compliance_warning
5. PII-only (no violation) still routes **clear** but logs a `WARNING` severity

---

## Operational Guidelines for Coding Agents

- **Code preservation**: Only modify code directly targeted by the user's request. Preserve all surrounding code, config values (e.g., `model`), comments, and formatting.
- **NEVER change the model** unless explicitly asked.
- **Model 404 errors**: Fix `GOOGLE_CLOUD_LOCATION` (e.g., `global` instead of `us-east1`), not the model name.
- **ADK tool imports**: Import the tool instance, not the module: `from google.adk.tools.load_web_page import load_web_page`
- **Run Python with `uv`**: `uv run python script.py`. Run `agents-cli install` first.
- **Stop on repeated errors**: If the same error appears 3+ times, fix the root cause instead of retrying.
- **Terraform conflicts** (Error 409): Use `terraform import` instead of retrying creation.
- **Workflow edge rules**: Workflow name must be a valid Python identifier (no hyphens). Conditional edges must use `Edge(from_node=..., to_node=..., route="...")` objects with `FunctionNode` instances (not plain functions). No duplicate `(source, target)` pairs.
- **MCPToolset**: Use `McpToolset` (not deprecated `MCPToolset`). Connection params use `StdioConnectionParams(server_params=StdioServerParameters(...))`.
- **Testing MCP tools in unit tests**: Import `app.mcp_server` directly and call the Python functions — do NOT start the FastMCP server process.
- **Integration test marker**: Use `@pytest.mark.live` for tests that require a live API key. Run with `pytest -m live` or exclude with `pytest -m "not live"`.
