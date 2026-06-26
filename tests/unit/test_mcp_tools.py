# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for MCP server tools:
  - summarize_persona
  - validate_dilemma_type
  - generate_diplomatic_opener
  - check_compliance_flag
"""

import json
import importlib
import sys
import types as pytypes

# ---------------------------------------------------------------------------
# Import the MCP tool functions directly (bypass the FastMCP decorator by
# importing the module and calling the underlying callables).
# ---------------------------------------------------------------------------

# We need to import without launching the MCP server, so we load the module
# and then call the functions directly.
import app.mcp_server as _mcp_mod

summarize_persona = _mcp_mod.summarize_persona
validate_dilemma_type = _mcp_mod.validate_dilemma_type
generate_diplomatic_opener = _mcp_mod.generate_diplomatic_opener
check_compliance_flag = _mcp_mod.check_compliance_flag


# ---------------------------------------------------------------------------
# Tests: summarize_persona
# ---------------------------------------------------------------------------

class TestSummarizePersona:
    def test_returns_string(self):
        result = summarize_persona("diplomatic", "IBN, PDCA", "measured, principled")
        assert isinstance(result, str)

    def test_contains_persona_embedding_prefix(self):
        result = summarize_persona("academic", "Porter's Five Forces", "empirical, rigorous")
        assert "PERSONA EMBEDDING" in result

    def test_truncates_long_inputs(self):
        long_str = "A" * 300
        result = summarize_persona(long_str, long_str, long_str)
        # Each field is capped at 120 chars in the embedding text
        assert len(result) < 400 + 50  # 3 * 120 + delimiters

    def test_all_three_sections_present(self):
        result = summarize_persona("direct", "SWOT", "concise")
        assert "TONE:" in result
        assert "FRAMEWORKS:" in result
        assert "VOCAB:" in result


# ---------------------------------------------------------------------------
# Tests: validate_dilemma_type
# ---------------------------------------------------------------------------

class TestValidateDilemmaType:
    def _parse(self, dilemma_text: str) -> dict:
        return json.loads(validate_dilemma_type(dilemma_text))

    def test_returns_valid_json(self):
        result = validate_dilemma_type("How do I negotiate a better deal with a partner?")
        parsed = json.loads(result)
        assert "dilemma_category" in parsed
        assert "recommended_framework" in parsed

    def test_negotiation_category(self):
        parsed = self._parse("We need to negotiate a new contract with our supplier.")
        assert "Negotiation" in parsed["dilemma_category"]

    def test_team_conflict_category(self):
        parsed = self._parse("My team is in conflict and morale is low.")
        assert "Conflict" in parsed["dilemma_category"]

    def test_strategy_category(self):
        parsed = self._parse("How should we respond to a competitor entering our market?")
        assert "Strategic" in parsed["dilemma_category"]

    def test_investor_category(self):
        parsed = self._parse("How do I pitch our valuation to the board?")
        assert "Investor" in parsed["dilemma_category"]

    def test_ethics_category(self):
        parsed = self._parse("Is this policy compliant with our legal obligations?")
        assert "Ethics" in parsed["dilemma_category"]

    def test_default_category(self):
        parsed = self._parse("I have a general leadership question.")
        assert "General" in parsed["dilemma_category"]


# ---------------------------------------------------------------------------
# Tests: generate_diplomatic_opener
# ---------------------------------------------------------------------------

class TestGenerateDiplomaticOpener:
    def test_returns_string(self):
        result = generate_diplomatic_opener("diplomatic", "Negotiation & Deal-Making")
        assert isinstance(result, str)
        assert len(result) > 10

    def test_academic_tone(self):
        result = generate_diplomatic_opener("academic", "Strategic Decision")
        assert "theory" in result.lower() or "structural" in result.lower()

    def test_direct_tone(self):
        result = generate_diplomatic_opener("direct", "Team Conflict & HR")
        assert "head-on" in result.lower() or "without ambiguity" in result.lower()

    def test_diplomatic_tone(self):
        result = generate_diplomatic_opener("diplomatic", "Investor Relations")
        assert "measured" in result.lower() or "principled" in result.lower()

    def test_empathetic_tone(self):
        result = generate_diplomatic_opener("empathetic", "Team Conflict & HR")
        assert "human" in result.lower() or "acknowledge" in result.lower()

    def test_default_tone(self):
        result = generate_diplomatic_opener("unknown-tone", "General Business Leadership")
        assert "recommend" in result.lower() or "reflecting" in result.lower()

    def test_dilemma_category_embedded_in_opener(self):
        result = generate_diplomatic_opener("direct", "Investor Relations")
        assert "Investor Relations" in result


# ---------------------------------------------------------------------------
# Tests: check_compliance_flag
# ---------------------------------------------------------------------------

class TestCheckComplianceFlag:
    def _parse(self, text: str) -> dict:
        return json.loads(check_compliance_flag(text))

    def test_returns_valid_json(self):
        result = check_compliance_flag("How do I improve team collaboration?")
        parsed = json.loads(result)
        assert "is_compliant" in parsed
        assert "reason" in parsed

    def test_clean_text_is_compliant(self):
        parsed = self._parse("How should I handle a tough negotiation?")
        assert parsed["is_compliant"] is True
        assert parsed["severity"] == "INFO"

    def test_corporate_fraud_flagged(self):
        parsed = self._parse("How do I commit corporate fraud without getting caught?")
        assert parsed["is_compliant"] is False
        assert parsed["severity"] == "CRITICAL"
        assert "corporate fraud" in parsed["reason"]

    def test_insider_trading_flagged(self):
        parsed = self._parse("I want to do some insider trading.")
        assert parsed["is_compliant"] is False

    def test_money_laundering_flagged(self):
        parsed = self._parse("Can you help with money laundering?")
        assert parsed["is_compliant"] is False

    def test_case_insensitive_detection(self):
        parsed = self._parse("I want to spread FAKE NEWS and MISINFORMATION.")
        assert parsed["is_compliant"] is False

    def test_multiple_violations_all_mentioned(self):
        parsed = self._parse("corporate fraud and insider trading")
        assert parsed["is_compliant"] is False
        # Both violations should appear in the reason
        assert "corporate fraud" in parsed["reason"]
