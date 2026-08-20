"""Gateway + Memory agent factory for AI soccer position agents.

Creates a Strands Agent that connects to an AgentCore Gateway via MCP,
giving each player access to tactical analysis tools (pass options,
open space finder, shot evaluator, defensive assignments), AND wires in
AgentCoreMemorySessionManager so each agent persists conversation history
across game ticks.

This module is used by the legacy deploy-all.sh flow, which passes
GATEWAY_URL and MEMORY_ID at deploy time. The CDK flow (deploy_all.py)
stages gateway_memory_agent_base_cdk.py under this module's name instead.
"""

import os
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig


def _create_gateway_transport():
    """Build a Streamable HTTP transport pointing at the AgentCore Gateway.

    Supports both NONE auth (no token) and token-based auth.
    """
    gateway_url = os.environ.get("GATEWAY_URL")
    if not gateway_url:
        raise RuntimeError("GATEWAY_URL environment variable is required")

    headers = {}
    access_token = os.environ.get("GATEWAY_ACCESS_TOKEN")
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    return streamablehttp_client(gateway_url, headers=headers)


def _create_session_manager(position_label: str) -> AgentCoreMemorySessionManager:
    """Build the AgentCore Memory (STM) session manager for this position."""
    memory_id = os.environ.get("MEMORY_ID")
    team_id = os.environ.get("TEAM_ID", "default-team")

    if not memory_id:
        raise RuntimeError("MEMORY_ID environment variable is required")

    return AgentCoreMemorySessionManager(
        agentcore_memory_config=AgentCoreMemoryConfig(
            memory_id=memory_id,
            session_id=f"match-{team_id}-{position_label}",
            actor_id=f"{team_id}-{position_label}",
        ),
        region_name=os.environ.get("AWS_DEFAULT_REGION"),
    )


def create_gateway_memory_agent(
    system_prompt: str,
    player_id: int,
    position_label: str,
    model_id: str = "us.amazon.nova-micro-v1:0",
) -> tuple[Agent, MCPClient]:
    """Create a Strands Agent with Gateway MCP tools AND AgentCore Memory (STM).

    Tools are fetched inside the MCPClient context so the connection is
    active when list_tools_sync() is called. Conversation history persists
    across game ticks through the memory session manager.

    Required env vars:
      GATEWAY_URL          — AgentCore Gateway MCP endpoint
      MEMORY_ID            — AgentCore Memory resource ID
      GATEWAY_ACCESS_TOKEN — Bearer token for Gateway auth (optional, NONE auth)
      TEAM_ID              — used as actor_id and session_id prefix

    Returns:
      (agent, mcp_client) — caller must use `with mcp_client:` context manager
      when invoking the agent so tools remain available.
    """
    mcp_client = MCPClient(_create_gateway_transport)
    model = BedrockModel(model_id=model_id)

    # Fetch tool definitions inside the context so the connection is active.
    with mcp_client:
        tools = mcp_client.list_tools_sync()

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        session_manager=_create_session_manager(position_label),
    )

    return agent, mcp_client
