"""Gateway + Memory agent factory for AI soccer position agents (CDK/npm-CLI flow).

Sibling of gateway_memory_agent_base.py with the same public API, for
deployments made with the npm AgentCore CLI (`python deploy_all.py`). There
the gateway, its Lambda tools, and the memory resource are all declared in
agentcore/agentcore.json ("tactical-tools" and "team_memory") and created by
the CDK app, which injects into every runtime:

  AGENTCORE_GATEWAY_TACTICAL_TOOLS_URL — the gateway MCP endpoint
  MEMORY_TEAM_MEMORY_ID                — the memory resource ID

No GATEWAY_URL or MEMORY_ID env vars are passed at deploy time.

deploy_all.py stages this file into each agent directory AS
gateway_memory_agent_base.py, so src/main.py imports it unchanged. The
original gateway_memory_agent_base.py remains the module staged by the
legacy deploy-all.sh flow. gateway_invoke_handler.py is flow-agnostic (it
reads no environment variables) and is shared by both flows.
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
    gateway_url = os.environ.get("AGENTCORE_GATEWAY_TACTICAL_TOOLS_URL")
    if not gateway_url:
        raise RuntimeError(
            "AGENTCORE_GATEWAY_TACTICAL_TOOLS_URL environment variable is "
            "required. It is injected automatically when the agent is deployed "
            "via `python deploy_all.py` with the tactical-tools gateway "
            "declared in agentcore/agentcore.json."
        )

    headers = {}
    access_token = os.environ.get("GATEWAY_ACCESS_TOKEN")
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    return streamablehttp_client(gateway_url, headers=headers)


def _create_session_manager(position_label: str) -> AgentCoreMemorySessionManager:
    """Build the AgentCore Memory (STM) session manager for this position."""
    memory_id = os.environ.get("MEMORY_TEAM_MEMORY_ID")
    team_id = os.environ.get("TEAM_ID", "default-team")

    if not memory_id:
        raise RuntimeError(
            "MEMORY_TEAM_MEMORY_ID environment variable is required. "
            "It is injected automatically when the agent is deployed via "
            "`python deploy_all.py` with the team_memory resource declared "
            "in agentcore/agentcore.json."
        )

    return AgentCoreMemorySessionManager(
        agentcore_memory_config=AgentCoreMemoryConfig(
            memory_id=memory_id,
            session_id=f"match-{team_id}-{position_label}",
            actor_id=f"{team_id}-{position_label}",
        ),
        # The CDK flow injects no region env var of its own; the AgentCore
        # runtime provides AWS_REGION. None lets boto3 resolve as a last resort.
        region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
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
      AGENTCORE_GATEWAY_TACTICAL_TOOLS_URL — injected by the CDK stack for
                                             the "tactical-tools" gateway
      MEMORY_TEAM_MEMORY_ID                — injected by the CDK stack for
                                             the "team_memory" resource
      GATEWAY_ACCESS_TOKEN                 — Bearer token (optional, NONE auth)
      TEAM_ID                              — actor/session prefix (optional;
                                             each team deploys into its own
                                             account, so the default cannot
                                             collide)

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
