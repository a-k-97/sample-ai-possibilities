# AI Team (Strands + Gateway + Memory) — Per-Position Soccer Agents with MCP Tactical Tools and Cross-Tick Recall

Five AI agents that each control a single player in a 5v5 soccer match, built with
[Strands Agents SDK](https://github.com/strands-agents/sdk-python) and combining
[Amazon Bedrock AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/)
(MCP-based tactical analysis tools) with
[Amazon Bedrock AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/)
(cross-tick history recall) in a single agent.

## What's Different from the Balanced Team?

Each agent gets **both** AgentCore capabilities at once:

**Gateway (tools):** every agent connects to an AgentCore Gateway via MCP and can
autonomously call tactical analysis tools during gameplay. The agent decides which
tools to use based on its current situation — no forced tool calls.

Available MCP tools:
- `calculate_pass_options` — Pass success probability based on interception risk
- `find_open_space` — Grid-based open space finder by zone (attack/midfield/defense)
- `evaluate_shot` — Shot success probability with aim recommendation
- `get_defensive_assignment` — Opponent threat ranking for marking priority

**Memory (recall):** every agent uses `AgentCoreMemorySessionManager` (STM) to
persist conversation history across game ticks, letting it recall opponent movement
patterns, previous tactical decisions, and which tool-guided plays worked earlier
in the match.

Key differences:
- The gateway with its four Lambda tools ("tactical-tools") AND the memory
  resource ("team_memory") are declared in `agentcore/agentcore.json` and
  created by the same `agentcore deploy` that deploys the agents
- The CDK stack injects the gateway endpoint as
  `AGENTCORE_GATEWAY_TACTICAL_TOOLS_URL` and the memory ID as
  `MEMORY_TEAM_MEMORY_ID` into every agent runtime, and grants the runtimes
  access to both
- `MCPClient` (gateway tools) and `AgentCoreMemorySessionManager` (memory)
  are wired into the same Strands Agent
  (`gateway_memory_agent_base_cdk.py`, staged into each agent at deploy time)
- `gateway_invoke_handler.py` wraps agent calls inside `with mcp_client:` context
- System prompts guide agents on WHEN to use tools and HOW to leverage recall,
  but agents decide autonomously
- Gateway uses NONE auth (no token required)

## Architecture

```
agents/
├── lib/                                 # Shared library (same as other teams)
└── ai-team-strands-gateway-memory/
    ├── ai-gk/                           # Goalkeeper  (player 0) — Nova Micro + Gateway + Memory
    ├── ai-def/                          # Defender    (player 1) — Nova Lite  + Gateway + Memory
    ├── ai-mid/                          # Midfielder  (player 2) — Nova Pro   + Gateway + Memory
    ├── ai-fwd1/                         # Forward 1   (player 3) — Nova Micro + Gateway + Memory
    ├── ai-fwd2/                         # Forward 2   (player 4) — Nova Lite  + Gateway + Memory
    ├── agentcore/                       # AgentCore project config (agents + gateway + tools + memory)
    │   ├── agentcore.json               # Runtimes + tactical-tools gateway + team_memory declarations
    │   └── cdk/                         # CDK app used by `agentcore deploy`
    ├── gateway_memory_agent_base_cdk.py # Agent factory: MCP client + memory session manager (CDK flow)
    ├── gateway_invoke_handler.py        # Invoke handler with MCP context (both flows)
    ├── gateway_tools/                   # Lambda handlers for tactical tools
    ├── deploy_all.py                    # Cross-platform deploy script
    ├── destroy_all.py                   # Cross-platform teardown script
    └── README.md
```

## How Agents Use Tools and Memory

Each agent's system prompt suggests which tools are most relevant for their position
and what to recall from earlier ticks, but the agent decides autonomously:

| Position | Primary Tools | Memory Focus |
|----------|--------------|--------------|
| GK | `get_defensive_assignment`, `calculate_pass_options` | Repeated shot patterns, dangerous shooters |
| DEF | `get_defensive_assignment`, `calculate_pass_options` | Dangerous runs, opponent attack patterns |
| MID | `calculate_pass_options`, `find_open_space`, `evaluate_shot` | Working passing lanes, pressing patterns |
| FWD1 | `evaluate_shot`, `calculate_pass_options`, `find_open_space` | Scoring positions, goalkeeper tendencies |
| FWD2 | `evaluate_shot`, `calculate_pass_options`, `find_open_space` | Combination plays, defender positioning |

## Prerequisites

- Python 3.10+
- Node.js 20+ and npm
- AWS CLI configured with valid credentials
- AgentCore CLI and CDK: `npm install -g @aws/agentcore aws-cdk`
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — used by the AgentCore CLI to package Python dependencies
- AWS account with Bedrock model access (Nova Micro, Lite, and/or Pro)
- Permissions for IAM, Lambda, CloudFormation, and Bedrock AgentCore
- CDK bootstrap (one-time per account/region): `cdk bootstrap aws://<account-id>/<region>`

Works on macOS, Linux, and Windows (PowerShell) — no WSL required.
No Python packages needed to deploy — `deploy_all.py` uses only the standard library.

## Deploy

Everything — the four Lambda tools, the MCP gateway, the memory resource, and
all five agents — is one CloudFormation deployment:

```bash
# macOS/Linux
AWS_DEFAULT_REGION=us-east-1 python deploy_all.py
```

```powershell
# Windows PowerShell
$env:AWS_DEFAULT_REGION = "us-east-1"
python deploy_all.py
```

The script checks prerequisites, writes the deploy target, bootstraps CDK if
needed, stages the shared `lib/`, `gateway_memory_agent_base_cdk.py`, and
`gateway_invoke_handler.py` into each agent directory, and runs
`agentcore deploy --yes`. That single deploy builds and deploys the Lambda
tools from `gateway_tools/`, creates the `tactical-tools` gateway with its
targets and IAM roles, creates the `team_memory` resource, grants the runtimes
access to both, and injects `AGENTCORE_GATEWAY_TACTICAL_TOOLS_URL` and
`MEMORY_TEAM_MEMORY_ID` into every agent — nothing to export or configure.

## Local Test

```bash
python3 ai-gk/test_local.py
```

## Teardown

```bash
python destroy_all.py            # remove all 5 agents
python destroy_all.py ai-gk      # remove one agent
```

The gateway, Lambda tools, and memory resource are kept; remove the
`agentCoreGateways` and `memories` entries from `agentcore/agentcore.json`
and redeploy (or delete the CloudFormation stack) to delete them.

## Legacy scripts

`deploy-all.sh` / `deploy-all-windows.ps1` (with `manage_gateway.py`,
`create_memory.py`, and `gateway_memory_agent_base.py`) are the previous
deployment path and still work. Note the two paths manage **separate
resources**: the legacy flow creates the `afwc-tactical-tools` gateway,
`afwc-gateway-tool-*` Lambdas, and an `AITeamGwMemMatchMemory` memory
outside CloudFormation, while this flow creates `tactical-tools`, its
Lambdas, and `team_memory` inside the stack. Running both against one
account leaves two gateways, two sets of Lambda functions, and two memory
resources.
