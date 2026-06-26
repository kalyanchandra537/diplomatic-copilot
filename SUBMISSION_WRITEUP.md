# SUBMISSION WRITEUP — Executive Diplomatic Co-Pilot

> **Track:** Agents for Business  
> **Framework:** Google ADK 2.0  
> **Model:** Gemini 2.5 Flash  

---

## Problem Statement

Senior professionals navigating high-stakes business environments — negotiations, board presentations, investor pitches, team conflicts — often lack access to a trusted advisor who knows their preferred communication style. Mentorship is scarce, expensive, and not available on-demand.

The **Executive Diplomatic Co-Pilot** addresses this gap: it learns *how* a specific business mentor, professor, or advisor communicates (their tone, frameworks, vocabulary) from raw text, and then answers the user's strategic dilemmas *in that mentor's voice* — acting as a personalized, always-available business advisor.

---

## Solution Architecture

```
                  ┌─────────────────────────────────────────────────────┐
                  │           ADK 2.0 Workflow (Directed Graph)          │
                  │                                                       │
  User Input ──▶  │  START → onboard_user (HITL ✋) → extraction_agent  │
                  │             │                                         │
                  │             ▼                                         │
                  │         get_dilemma (HITL ✋) → security_checkpoint  │
                  │                                    │                  │
                  │               ┌──── "clear" ───────┤                  │
                  │               │                    │ "security_       │
                  │               │                    │  violated"       │
                  │               ▼                    ▼                  │
                  │          orchestrator      compliance_warning         │
                  │               │                    │                  │
                  │               ▼                    │                  │
                  │          format_output ────────────┘                  │
                  │               │                                       │
                  │               ▼                                       │
  Final Advice ◀──│           final_node                                 │
                  └─────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────┐
  │  MCP Server (stdio subprocess — mcp_server.py)  │
  │  Tools used by extraction_agent + orchestrator: │
  │  • summarize_persona                             │
  │  • validate_dilemma_type                         │
  │  • generate_diplomatic_opener                    │
  │  • check_compliance_flag                         │
  └─────────────────────────────────────────────────┘
```

---

## ADK Concepts Used

### ADK Workflow (Directed Graph)
**File:** [`app/agent.py`](app/agent.py)

The entire application is structured as an ADK 2.0 `Workflow` — a directed acyclic graph where each node is either a `FunctionNode`, a `@node`-decorated async generator, or an `LlmAgent`. Edges are declared explicitly, with conditional routing via `Edge(from_node=..., to_node=..., route="...")` to implement the security branching.

### LlmAgent (×3)
**File:** [`app/agent.py`](app/agent.py)

- **`extraction_agent`** — dedicated to analyzing mentor text and returning a structured `PersonaSummary` (Pydantic schema) saved to `ctx.state["persona_summary"]`.
- **`execution_agent`** — the persona embodiment agent; generates diplomatic advice in the mentor's voice.
- **`orchestrator`** — coordinates the full response: classifies the dilemma via MCP, gets a tone-matched opener via MCP, delegates generation to `execution_agent` via `AgentTool`.

### AgentTool
**File:** [`app/agent.py`](app/agent.py) — line ~94

`AgentTool(execution_agent)` is registered in the orchestrator's `tools` list. This enables the orchestrator to call `execution_agent` as a tool call mid-inference, passing the dilemma and persona context.

### ctx.state (Inter-Node Data Sharing)
**File:** [`app/agent.py`](app/agent.py) — multiple nodes

Session state is used throughout:
- `ctx.state["mentor_text"]` — raw mentor transcript from onboarding
- `ctx.state["persona_summary"]` — structured persona (tone, frameworks, vocabulary)  
- `ctx.state["user_dilemma"]` — scrubbed dilemma text
- `ctx.state["final_advice"]` — formatted output from orchestrator

Template substitution `{persona_summary}` in LlmAgent instructions reads directly from state.

### RequestInput (Human-in-the-Loop)
**File:** [`app/agent.py`](app/agent.py) — `onboard_user`, `get_dilemma` nodes

Two HITL pause points:
1. **Onboarding** — collects `profile_name` and `mentor_text` (the raw transcript)
2. **Dilemma** — shows the extracted persona summary, then collects the user's business question

### MCP Server + MCPToolset
**Files:** [`app/mcp_server.py`](app/mcp_server.py), [`app/agent.py`](app/agent.py)

The MCP server runs as a stdio subprocess, launched by `StdioConnectionParams`. Both `extraction_agent` and `orchestrator` have `McpToolset` in their `tools` list.

### Agents CLI
**Files:** [`GEMINI.md`](GEMINI.md), [`Makefile`](Makefile), [`agents-cli-manifest.yaml`](agents-cli-manifest.yaml)

Project scaffolded with `agents-cli scaffold create`. Development lifecycle managed via `make playground`, `make test`, `make lint`. Full Terraform deployment config generated in `deployment/terraform/single-project/`.

---

## Security Design

### Layer 1: PII Scrubbing
**Why it matters:** Mentor transcripts and business dilemmas often contain confidential personal information (email addresses, direct-dial numbers, employee IDs). Passing raw PII to an LLM creates GDPR/CCPA exposure.

**Implementation:** Regex patterns scrub emails, US phone numbers (both dash and dot formats), and 9–12 digit ID numbers before the text is ever passed to an LLM. Scrubbed values are replaced with `[REDACTED_EMAIL]`, `[REDACTED_PHONE]`, `[REDACTED_ID]`.

### Layer 2: Prompt Injection Detection
**Why it matters:** Business users are savvy; a bad actor could embed `"ignore previous instructions"` inside a fake "mentor transcript" to manipulate the agent's behavior.

**Implementation:** 7 injection patterns are detected (case-insensitive):
- `ignore previous instructions`, `system prompt`, `override rules`
- `jailbreak`, `developer mode`, `disregard instructions`, `pretend you are`

Any match triggers `route = "security_violated"` → `compliance_warning` node — the LLM is never called.

### Layer 3: Corporate Compliance Filter
**Why it matters:** An enterprise business advisor must never facilitate illegal or unethical activity, regardless of how the request is framed.

**Implementation:** 8 compliance violation terms are checked:
`corporate fraud`, `insider trading`, `fake news`, `misinformation`, `impersonate a public official`, `malicious impersonation`, `toxic content`, `money laundering`

### Layer 4: Structured Audit Log
Every checkpoint evaluation produces a JSON audit log with `timestamp`, `severity` (INFO/WARNING/CRITICAL), `status` (clear/pii_redacted/violation), and boolean flags for each check type. This provides a traceable compliance trail.

### Routing Logic
PII-only detections still **route clear** (the redacted text continues to the LLM) with a `WARNING` severity log. Only injection attacks and compliance violations **block** the request entirely.

---

## MCP Server Design

**File:** [`app/mcp_server.py`](app/mcp_server.py) — FastMCP stdio transport

| Tool | Purpose | Used By |
|---|---|---|
| `summarize_persona` | Compresses tone/frameworks/vocabulary into a compact persona embedding string (capped at 120 chars per field) | `extraction_agent` |
| `validate_dilemma_type` | Keyword-classifies the user's dilemma into 6 strategic categories (Negotiation, HR, Strategy, Investor, Ethics, General) and returns the recommended reasoning framework | `orchestrator` |
| `generate_diplomatic_opener` | Generates a tone-matched opening sentence for the diplomatic response, using the persona tone and dilemma category | `orchestrator` |
| `check_compliance_flag` | Pre-screens text against 8 compliance violation terms before calling the security checkpoint FunctionNode (defense-in-depth) | `orchestrator` |

The MCP server is launched as a subprocess by each agent's `McpToolset` on first tool call. No persistent process is needed — stdio transport handles the lifecycle automatically.

---

## HITL Flow

The Workflow uses two `RequestInput` pause points:

### Screen 1 — Secure Onboarding
```
Interrupts on: profile_name (then mentor_text)
Shows: Welcome message + instructions for pasting mentor transcripts
Saves to: ctx.state["profile_name"], ctx.state["mentor_text"]
```
This gates the entire system behind a deliberate user action — no LLM call happens until the user has provided both their identity and their mentor's text.

### Screen 2 — Dilemma Solver Playground
```
Interrupts on: user_dilemma
Shows: Extracted persona summary (tone + frameworks from extraction_agent)
       Compliance Status badge
Saves to: ctx.state["user_dilemma"]
```
The user sees the extracted persona *before* submitting their dilemma, giving them feedback on the quality of the persona extraction and a chance to refine before proceeding.

---

## Demo Walkthrough

Three sample test cases (also in README):

### Case 1 — Negotiation Dilemma (happy path)
**Mentor text:** *"I always believe in finding the win-win. Approach every negotiation with curiosity, not confrontation. Use the IBN framework — separate people from positions. My favorite phrase is 'What would make this work for both of us?'"*

**Dilemma:** *"My supplier is asking for a 40% price increase. How should I respond?"*

**Expected flow:** onboard_user → extraction_agent (extracts diplomatic/IBN persona) → get_dilemma → security_checkpoint (clear) → orchestrator → format_output → final_node

**Expected output:** A diplomatically framed response using IBN language, opening with a persona-matched phrase, categorized as "Negotiation & Deal-Making"

---

### Case 2 — Compliance Blocked (security path)
**Dilemma:** *"How do I commit insider trading without getting caught?"*

**Expected flow:** security_checkpoint routes `security_violated` → compliance_warning → final_node

**Expected output:** "⚠️ Compliance Violation Warning — Blocked ❌"

---

### Case 3 — PII Scrubbing (warning path, continues)
**Dilemma:** *"My colleague john.doe@corp.com called 555-867-5309 to tell me our CFO wants to fire me. What should I do?"*

**Expected flow:** security_checkpoint scrubs PII (route = "clear", severity = WARNING) → orchestrator gets scrubbed text → generates HR/conflict advice

**Expected output:** Response using `[REDACTED_EMAIL]` and `[REDACTED_PHONE]` in the audit log; advice addresses the team conflict professionally

---

## Impact / Value Statement

**Who benefits:**
- MBA students and early-career professionals without access to experienced mentors
- Executives who work with a consistent advisor style and want consistency at scale
- Business schools and corporate training programs that can encode a faculty member's teaching style into an AI advisor

**Why it matters:**
Behavioral modeling from text is the key insight — unlike generic AI assistants, this agent doesn't give you its own voice; it gives you the voice of someone you've already decided to trust. The security guardrails ensure this trust is not exploitable.

**The ADK advantage:**
The Workflow graph API makes the multi-step persona extraction → security → advice pipeline explicit, auditable, and modifiable without touching business logic. Adding a new guardrail node is a single edge addition, not a prompt rewrite.
