"""
MCP Server for Executive Diplomatic Co-Pilot.
Provides 4 domain-specific tools accessible by the extraction_agent and orchestrator.
Transport: stdio (standard MCP Python SDK pattern).
"""

import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("diplomatic-copilot-mcp")


@mcp.tool()
def summarize_persona(
    tone_traits: str,
    frameworks: str,
    vocabulary: str,
) -> str:
    """Compress extracted persona attributes into a compact semantic embedding text.

    Use this tool to create a token-efficient persona summary that will be injected
    into the diplomatic execution agent's context without passing raw transcripts.

    Args:
        tone_traits: Linguistic tone and styling traits of the mentor.
        frameworks: Key professional frameworks the mentor uses.
        vocabulary: Frequently used words, idioms, or phrasing patterns.

    Returns:
        A compact persona embedding string for downstream agent use.
    """
    summary = (
        f"PERSONA EMBEDDING | "
        f"TONE: {tone_traits[:120]} | "
        f"FRAMEWORKS: {frameworks[:120]} | "
        f"VOCAB: {vocabulary[:120]}"
    )
    return summary


@mcp.tool()
def validate_dilemma_type(dilemma_text: str) -> str:
    """Classify a business dilemma into a known strategic category.

    Use this tool to categorize user input before diplomatic resolution so the
    execution agent can apply the most relevant reasoning framework.

    Args:
        dilemma_text: The business dilemma or question submitted by the user.

    Returns:
        JSON string with dilemma_category and recommended_framework fields.
    """
    text = dilemma_text.lower()

    if any(kw in text for kw in ["negotiation", "deal", "contract", "partner"]):
        category = "Negotiation & Deal-Making"
        framework = "Interest-Based Negotiation (IBN)"
    elif any(kw in text for kw in ["conflict", "team", "resign", "performance", "fire"]):
        category = "Team Conflict & HR"
        framework = "Non-Violent Communication (NVC) + Situational Leadership"
    elif any(kw in text for kw in ["strategy", "market", "pivot", "growth", "competitor"]):
        category = "Strategic Decision"
        framework = "Porter's Five Forces + SWOT Analysis"
    elif any(kw in text for kw in ["investor", "board", "pitch", "funding", "valuation"]):
        category = "Investor Relations"
        framework = "Balanced Scorecard + Stakeholder Theory"
    elif any(kw in text for kw in ["ethics", "compliance", "legal", "policy"]):
        category = "Ethics & Compliance"
        framework = "Deontological Ethics + Risk Management Framework"
    else:
        category = "General Business Leadership"
        framework = "First Principles Thinking + PDCA Cycle"

    return json.dumps({
        "dilemma_category": category,
        "recommended_framework": framework,
    })


@mcp.tool()
def generate_diplomatic_opener(tone: str, dilemma_category: str) -> str:
    """Generate a context-appropriate opening phrase for a diplomatic response.

    Use this tool to craft the opening line of a business advisor's response
    aligned with the mentor persona's tone and the dilemma category.

    Args:
        tone: The tone descriptor extracted from the mentor persona (e.g., 'academic, direct').
        dilemma_category: The strategic category of the dilemma.

    Returns:
        A diplomatic opening sentence string.
    """
    tone_lower = tone.lower()

    if "academic" in tone_lower:
        opener = f"Drawing from established theory in {dilemma_category}, one must first examine the underlying structural forces at play."
    elif "direct" in tone_lower:
        opener = f"Let's address this {dilemma_category} challenge head-on, without ambiguity."
    elif "diplomatic" in tone_lower:
        opener = f"In navigating this {dilemma_category} situation, I would counsel a measured and principled approach."
    elif "empathetic" in tone_lower:
        opener = f"Before responding to this {dilemma_category} challenge, it's important to acknowledge the human dimensions involved."
    else:
        opener = f"Reflecting carefully on this {dilemma_category} matter, I would recommend the following course of action."

    return opener


@mcp.tool()
def check_compliance_flag(text: str) -> str:
    """Pre-screen text for compliance violations before generating advice.

    Use this tool as a lightweight domain-specific compliance pre-check before
    calling the main security checkpoint node to reduce unnecessary LLM calls.

    Args:
        text: The user input or generated response text to screen.

    Returns:
        JSON string with is_compliant flag and reason.
    """
    violations = [
        "corporate fraud",
        "insider trading",
        "fake news",
        "misinformation",
        "impersonate a public official",
        "malicious impersonation",
        "money laundering",
        "toxic content",
    ]

    flagged = [v for v in violations if v in text.lower()]

    if flagged:
        return json.dumps({
            "is_compliant": False,
            "reason": f"Content matches compliance violation terms: {', '.join(flagged)}",
            "severity": "CRITICAL",
        })

    return json.dumps({
        "is_compliant": True,
        "reason": "No compliance violations detected.",
        "severity": "INFO",
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
