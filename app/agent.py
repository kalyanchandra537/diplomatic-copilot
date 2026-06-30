import os
import sys
import re
import json
import datetime
from typing import Any

from google.adk.apps import App
from google.adk.workflow import Workflow, node, FunctionNode, Edge, RetryConfig
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset as MCPToolset, StdioConnectionParams, StdioServerParameters
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, Field

from app.config import config

# MCP server command — launches mcp_server.py as a subprocess via stdio
_MCP_SERVER_PARAMS = StdioConnectionParams(
    server_params=StdioServerParameters(
        command=sys.executable,
        args=[str(os.path.join(os.path.dirname(__file__), "mcp_server.py"))],
    )
)

# -----------------------------------------------------------------------------
# 1. Pydantic Models for Input / Output Validation
# -----------------------------------------------------------------------------

class PersonaSummary(BaseModel):
    tone_traits: str = Field(description="Linguistic tone and styling traits of the mentor.")
    frameworks: str = Field(description="Key professional frameworks or conceptual filters used by the mentor.")
    vocabulary: str = Field(description="Frequently used words, idioms, or phrasing patterns of the mentor.")
    summary_embedding_text: str = Field(description="A highly compact, token-efficient semantic representation of the persona.")


# -----------------------------------------------------------------------------
# 2. Specialized Sub-Agents
# -----------------------------------------------------------------------------

# Specialized Agent 1: Behavioral Extraction Agent
# Wired to MCP tools: summarize_persona, validate_dilemma_type, check_compliance_flag
extraction_agent = LlmAgent(
    name="extraction_agent",
    model=Gemini(model=config.model, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction="""Analyze the provided mentor text/transcript.
Extract:
1. Tone traits (e.g., diplomatic, direct, academic)
2. Professional frameworks or conceptual models
3. Vocabulary styling (words, phrasing)
4. A highly compact 'summary_embedding_text' representing the persona for downstream LLM prompts.

Use the summarize_persona tool to compress the extracted traits into a compact embedding text.
Respond strictly with the JSON schema required.
""",
    output_schema=PersonaSummary,
    output_key="persona_summary",  # Saves in ctx.state['persona_summary']
    tools=[MCPToolset(connection_params=_MCP_SERVER_PARAMS)],
)

# Specialized Agent 2: Diplomatic Execution Agent
execution_agent = LlmAgent(
    name="execution_agent",
    model=Gemini(model=config.model, retry_options=types.HttpRetryOptions(attempts=3)),
    description="Generates a strategic, diplomatic business advice response in the style of the extracted mentor persona.",
    instruction="""You are a Diplomatic Execution Agent embodying a mentor persona.
Using the mentor persona summary provided: {persona_summary}
Answer the following business dilemma wisely and diplomatically.
Strictly adhere to the mentor's tone, professional frameworks, and vocabulary.
""",
)


# -----------------------------------------------------------------------------
# 3. Orchestrator Agent (delegates to execution_agent via AgentTool)
# -----------------------------------------------------------------------------

orchestrator = LlmAgent(
    name="orchestrator",
    model=Gemini(model=config.model, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction="""You are the Executive Diplomatic Co-Pilot Orchestrator.
The mentor persona summary is available in state: {persona_summary}.
The user's dilemma is: {user_dilemma}.

1. Use the validate_dilemma_type MCP tool to classify the dilemma into its strategic category.
2. Use the generate_diplomatic_opener MCP tool to get an appropriate opening phrase.
3. Call the execution_agent tool to generate a diplomatic resolution, passing both the dilemma and persona summary.
4. Return a polished, mentor-persona-styled answer.
""",
    tools=[AgentTool(execution_agent), MCPToolset(connection_params=_MCP_SERVER_PARAMS)],
    output_key="final_advice",
)


# -----------------------------------------------------------------------------
# 4. Workflow Function Nodes
# -----------------------------------------------------------------------------

@node(rerun_on_resume=True)
async def onboard_user(ctx: Context, node_input: Any):
    """Secure onboarding: collects user profile and mentor transcript (HITL)."""
    if not ctx.resume_inputs or "profile_name" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="profile_name",
            message=(
                "👤 **Unified Dashboard — Secure Onboarding**\n\n"
                "Welcome to the Executive Diplomatic Co-Pilot Unified Dashboard.\n"
                "Please create your profile by entering your Name and Title.\n"
                "Example: Jane Doe, Chief of Staff"
            )
        )
        return

    if "mentor_text" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="mentor_text",
            message=(
                "📄 **Unified Dashboard — Mentor Transcript Ingestion**\n\n"
                "Please paste transcripts, speeches, or written behavioral descriptions "
                "of your ideal business mentor or professor.\n\n"
                "The system will extract their linguistic style and professional frameworks."
            )
        )
        return

    profile = ctx.resume_inputs["profile_name"]
    mentor_text = ctx.resume_inputs["mentor_text"]

    yield Event(
        output=mentor_text,
        state={
            "profile_name": profile,
            "mentor_text": mentor_text,
        }
    )


@node(rerun_on_resume=True)
async def get_dilemma(ctx: Context, node_input: Any):
    """Collects the user's business dilemma via HITL (Screen 2)."""
    if not ctx.resume_inputs or "user_dilemma" not in ctx.resume_inputs:
        persona = ctx.state.get("persona_summary", {})
        tone = persona.get("tone_traits", "Diplomatic & Insightful")
        frameworks = persona.get("frameworks", "Strategic leadership thinking")

        yield RequestInput(
            interrupt_id="user_dilemma",
            message=(
                "🎭 **Unified Dashboard — Dilemma Solver**\n\n"
                f"**Extracted Mentor Persona:**\n"
                f"- Tone: {tone}\n"
                f"- Frameworks: {frameworks}\n\n"
                "**Compliance Status: Clear ✅**\n\n"
                "Please enter your tricky business dilemma, interview question, or strategic problem:"
            )
        )
        return

    dilemma = ctx.resume_inputs["user_dilemma"]
    yield Event(output=dilemma, state={"user_dilemma": dilemma})


def _security_checkpoint_fn(ctx: Context, node_input: Any) -> Event:
    """Security node: PII scrubbing + injection detection + compliance check + audit log."""
    text = str(node_input) if not isinstance(node_input, str) else node_input

    # PII Scrubbing
    scrubbed = text
    scrubbed = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', scrubbed)
    scrubbed = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', scrubbed)
    scrubbed = re.sub(r'\b\d{9,12}\b', '[REDACTED_ID]', scrubbed)

    # Injection detection
    injection_keywords = [
        "ignore previous instructions",
        "system prompt",
        "override rules",
        "jailbreak",
        "developer mode",
        "disregard instructions",
        "pretend you are",
    ]
    has_injection = any(kw in scrubbed.lower() for kw in injection_keywords)

    # Corporate compliance filter (domain-specific rule: business ethics)
    compliance_violations = [
        "corporate fraud",
        "insider trading",
        "fake news",
        "misinformation",
        "impersonate a public official",
        "malicious impersonation",
        "toxic content",
        "money laundering",
    ]
    has_violation = any(kw in scrubbed.lower() for kw in compliance_violations)

    severity = "CRITICAL" if (has_injection or has_violation) else ("WARNING" if scrubbed != text else "INFO")
    status = "violation" if (has_injection or has_violation) else ("pii_redacted" if scrubbed != text else "clear")

    audit_log = {
        "timestamp": datetime.datetime.now().isoformat(),
        "severity": severity,
        "event": "security_checkpoint",
        "status": status,
        "pii_scrubbed": scrubbed != text,
        "injection_detected": has_injection,
        "compliance_violated": has_violation,
    }
    print(f"AUDIT LOG: {json.dumps(audit_log)}")

    route = "security_violated" if (has_injection or has_violation) else "clear"

    return Event(
        output=scrubbed,
        state={"security_audit_log": audit_log, "user_dilemma": scrubbed},
        route=route,
    )


def _compliance_warning_fn(ctx: Context, node_input: Any) -> Event:
    """Outputs a Compliance Violation Warning instead of advice."""
    warning_msg = (
        "⚠️ **Compliance Violation Warning**\n\n"
        "Your prompt or the generated response attempts to mimic corporate fraud, "
        "spread misinformation, impersonate a specific live public official maliciously, "
        "or generate toxic content.\n\n"
        "**Compliance Status: Blocked ❌**\n\n"
        "Please rephrase your question to comply with ethical and legal standards."
    )
    return Event(
        output={"advice": "BLOCKED", "status": "Blocked"},
        content=types.Content(role="model", parts=[types.Part.from_text(text=warning_msg)])
    )


def _format_output_fn(ctx: Context, node_input: Any) -> Event:
    """Formats the orchestrator's response with the persona and compliance badge."""
    text = ""
    if isinstance(node_input, types.Content) and node_input.parts:
        text = "".join(part.text for part in node_input.parts if hasattr(part, "text") and part.text)
    elif isinstance(node_input, str):
        text = node_input
    elif isinstance(node_input, dict):
        text = node_input.get("advice", str(node_input))

    final_advice = ctx.state.get("final_advice", text)

    output_text = (
        f"### 🎯 Strategic Advisor Response\n\n"
        f"{final_advice or text}\n\n"
        f"---\n**Compliance Status: Clear ✅**"
    )
    return Event(
        output={"advice": final_advice or text, "status": "Clear"},
        content=types.Content(role="model", parts=[types.Part.from_text(text=output_text)])
    )


def _final_node_fn(ctx: Context, node_input: Any) -> Event:
    """Terminal node: passes final output through."""
    return Event(output=node_input)


# Wrap plain functions as FunctionNode so they can be used as BaseNode in Edge
security_checkpoint = FunctionNode(func=_security_checkpoint_fn, name="security_checkpoint")
compliance_warning = FunctionNode(func=_compliance_warning_fn, name="compliance_warning")
format_output = FunctionNode(func=_format_output_fn, name="format_output")
final_node = FunctionNode(func=_final_node_fn, name="final_node")


# -----------------------------------------------------------------------------
# 5. Workflow Graph — Edge definitions using Edge objects for conditional routes
# Note: No duplicate (source, target) pairs to avoid Pydantic ValidationError
# -----------------------------------------------------------------------------

edges = [
    # Sequential onboarding → extraction
    ("START", onboard_user),
    (onboard_user, extraction_agent),
    (extraction_agent, get_dilemma),
    # Security gate: get_dilemma → security_checkpoint
    (get_dilemma, security_checkpoint),
    # Conditional routes from security_checkpoint (each goes to a DIFFERENT target)
    Edge(from_node=security_checkpoint, to_node=orchestrator, route="clear"),
    Edge(from_node=security_checkpoint, to_node=compliance_warning, route="security_violated"),
    # Orchestrator → format_output
    (orchestrator, format_output),
    # Both format_output and compliance_warning → final_node (different sources, one unconditional edge each)
    (format_output, final_node),
    (compliance_warning, final_node),
]

root_agent = Workflow(
    name="diplomatic_copilot_workflow",
    edges=edges,
    description="Executive Diplomatic Co-Pilot — Unified Dashboard · Multi-Agent Workflow with Security Guardrails",
)

app = App(
    root_agent=root_agent,
    name="app",
)
