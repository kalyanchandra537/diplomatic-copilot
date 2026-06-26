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
Integration tests for the Executive Diplomatic Co-Pilot agent.

Tests that the root_agent (Workflow) and the App are properly configured,
and that the Runner can be instantiated. Full end-to-end streaming tests
require a live GOOGLE_API_KEY and network access, so they are skipped in
offline / unit CI environments via the `live` mark.
"""

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from app.agent import root_agent, app
from app import app as app_module_export


# ---------------------------------------------------------------------------
# Smoke tests: structural validation (no API calls)
# ---------------------------------------------------------------------------

class TestAgentStructure:
    def test_root_agent_name(self):
        """Workflow must have a valid Python identifier as name."""
        assert root_agent.name == "diplomatic_copilot_workflow"
        assert root_agent.name.isidentifier()

    def test_root_agent_description(self):
        """Workflow description must be non-empty."""
        assert root_agent.description
        assert len(root_agent.description) > 10

    def test_app_name(self):
        """App instance must be named 'app'."""
        assert app.name == "app"

    def test_app_module_export(self):
        """app/__init__.py must export 'app' correctly."""
        assert app_module_export is app

    def test_runner_instantiation(self):
        """Runner must accept a Workflow as the agent argument."""
        session_service = InMemorySessionService()
        runner = Runner(
            agent=root_agent,
            session_service=session_service,
            app_name="test",
        )
        assert runner is not None


# ---------------------------------------------------------------------------
# Live integration test: requires GOOGLE_API_KEY and real API access.
# Run with: uv run pytest tests/integration -m live
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_agent_stream() -> None:
    """
    Integration test for the agent stream functionality.
    Tests that the workflow agent returns valid streaming responses.

    Note: The Diplomatic Co-Pilot uses HITL (Human-in-the-Loop) onboarding,
    so a direct stream test will hit the first RequestInput interrupt.
    We verify the runner produces at least one event.
    """
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="Hello")]
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    assert len(events) > 0, "Expected at least one event from the workflow"
