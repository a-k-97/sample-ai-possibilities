#!/usr/bin/env python3
"""Create/reuse MCP Gateway and register Lambda targets via boto3.

Usage:
  python3 manage_gateway.py

Outputs (to stdout, one per line):
  GATEWAY_ID=<id>
  GATEWAY_URL=<url>

Env vars required:
  AWS_DEFAULT_REGION (default: us-east-1)
  GATEWAY_ROLE_ARN   — IAM role for the gateway
  LAMBDA_PREFIX      — e.g. afwc-gateway-tool
  AWS_ACCOUNT_ID     — AWS account ID
"""

import os
import sys
import json
import time
import boto3

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
GATEWAY_NAME = os.environ.get("GATEWAY_NAME", "afwc-tactical-tools")
ROLE_ARN = os.environ["GATEWAY_ROLE_ARN"]
ACCOUNT_ID = os.environ["AWS_ACCOUNT_ID"]
LAMBDA_PREFIX = os.environ.get("LAMBDA_PREFIX", "afwc-gateway-tool")

# Reusable schema fragments — the schemas MUST match what the Lambda handlers
# in gateway_tools/ actually read from the event body (passer_position,
# teammates, opponents, ...), NOT a raw game_state blob. The agent builds
# these small inputs from the positions in its state summary.
_XY = {
    "type": "object",
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
    "required": ["x", "y"],
}
_TEAM_SIDE = {
    "type": "string",
    "enum": ["HOME", "AWAY"],
    "description": "Your team side: HOME if your goal is at x=-55, AWAY if your goal is at x=+55",
}

TOOLS = [
    {
        "name": "calculate-pass-options",
        "lambda_suffix": "calculate-pass-options",
        "description": "Calculate pass success probability based on interception risk",
        "schema": [
            {
                "name": "calculate_pass_options",
                "description": "Calculate pass success probability for each teammate based on distance and interception risk",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "passer_position": {**_XY, "description": "Your current position"},
                        "teammates": {
                            "type": "array",
                            "description": "Your teammates from the Teammates list (id and position)",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "player_id": {"type": "integer"},
                                    "position": _XY,
                                },
                                "required": ["player_id", "position"],
                            },
                        },
                        "opponents": {
                            "type": "array",
                            "description": "Opponent players from the Opponents list",
                            "items": {
                                "type": "object",
                                "properties": {"position": _XY},
                                "required": ["position"],
                            },
                        },
                    },
                    "required": ["passer_position", "teammates", "opponents"],
                },
            }
        ],
    },
    {
        "name": "evaluate-shot",
        "lambda_suffix": "evaluate-shot",
        "description": "Evaluate shot success probability with aim recommendation",
        "schema": [
            {
                "name": "evaluate_shot",
                "description": "Evaluate shot success probability and recommend aim point and power",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "shooter_position": {**_XY, "description": "Your current position"},
                        "goalkeeper_position": {**_XY, "description": "The OPPONENT goalkeeper's position (usually OPP0)"},
                        "team_side": _TEAM_SIDE,
                        "blocker_positions": {
                            "type": "array",
                            "description": "Positions of opponents between you and the goal (optional)",
                            "items": _XY,
                        },
                    },
                    "required": ["shooter_position", "goalkeeper_position", "team_side"],
                },
            }
        ],
    },
    {
        "name": "find-open-space",
        "lambda_suffix": "find-open-space",
        "description": "Find open space on the field by zone",
        "schema": [
            {
                "name": "find_open_space",
                "description": "Grid-based open space finder by zone (attack/midfield/defense)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "opponent_positions": {
                            "type": "array",
                            "description": "Positions of all opponent players from the Opponents list",
                            "items": _XY,
                        },
                        "zone": {
                            "type": "string",
                            "enum": ["attack", "midfield", "defense"],
                            "description": "Zone to find space in, relative to your team's attacking direction",
                        },
                        "team_side": _TEAM_SIDE,
                        "my_position": {**_XY, "description": "Your current position"},
                    },
                    "required": ["opponent_positions", "zone", "team_side", "my_position"],
                },
            }
        ],
    },
    {
        "name": "get-defensive-assignment",
        "lambda_suffix": "get-defensive-assignment",
        "description": "Get opponent threat ranking for marking priority",
        "schema": [
            {
                "name": "get_defensive_assignment",
                "description": "Rank opponent threats and recommend who to MARK and how tightly",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "opponents": {
                            "type": "array",
                            "description": "Opponent players from the Opponents list (id and position)",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "player_id": {"type": "integer"},
                                    "position": _XY,
                                },
                                "required": ["player_id", "position"],
                            },
                        },
                        "ball": {
                            "type": "object",
                            "description": "Ball position, plus possession_player_id if an opponent holds it",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "possession_player_id": {"type": "integer"},
                            },
                            "required": ["x", "y"],
                        },
                        "my_position": {**_XY, "description": "Your current position"},
                        "team_side": _TEAM_SIDE,
                    },
                    "required": ["opponents", "ball", "my_position", "team_side"],
                },
            }
        ],
    },
]

client = boto3.client("bedrock-agentcore-control", region_name=REGION)


def find_existing_gateway():
    """Return gateway dict if it already exists, else None."""
    resp = client.list_gateways()
    for gw in resp.get("items", []):
        if gw.get("name") == GATEWAY_NAME:
            return gw
    return None


def create_gateway():
    """Create MCP gateway with NONE auth."""
    print(f"  Creating MCP Gateway: {GATEWAY_NAME} (NONE auth)", file=sys.stderr)
    resp = client.create_gateway(
        name=GATEWAY_NAME,
        roleArn=ROLE_ARN,
        protocolType="MCP",
        protocolConfiguration={"mcp": {"searchType": "SEMANTIC"}},
        authorizerType="NONE",
    )
    return resp["gatewayId"]


def wait_for_gateway(gateway_id, max_wait=150):
    """Poll until gateway is READY/ACTIVE."""
    for _ in range(max_wait // 5):
        resp = client.get_gateway(gatewayIdentifier=gateway_id)
        status = resp.get("status", "UNKNOWN")
        if status in ("READY", "ACTIVE", "AVAILABLE"):
            print(f"  ✅ Gateway is {status}", file=sys.stderr)
            return True
        print(f"  Status: {status} (waiting...)", file=sys.stderr)
        time.sleep(5)
    print("  ⚠️  Gateway did not become ready in time", file=sys.stderr)
    return False


def register_targets(gateway_id):
    """Register Lambda targets if not already registered."""
    existing = set()
    try:
        resp = client.list_gateway_targets(gatewayIdentifier=gateway_id)
        for t in resp.get("items", []):
            existing.add(t.get("name"))
    except Exception:
        pass

    for tool in TOOLS:
        if tool["name"] in existing:
            print(f"  Already registered: {tool['name']}", file=sys.stderr)
            continue

        lambda_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{LAMBDA_PREFIX}-{tool['lambda_suffix']}"
        print(f"  Registering: {tool['name']} -> {lambda_arn}", file=sys.stderr)
        try:
            client.create_gateway_target(
                gatewayIdentifier=gateway_id,
                name=tool["name"],
                description=tool["description"],
                targetConfiguration={
                    "mcp": {
                        "lambda": {
                            "lambdaArn": lambda_arn,
                            "toolSchema": {"inlinePayload": tool["schema"]},
                        }
                    }
                },
                credentialProviderConfigurations=[
                    {"credentialProviderType": "GATEWAY_IAM_ROLE"}
                ],
            )
        except client.exceptions.ConflictException:
            print(f"  Already registered (conflict): {tool['name']}", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  Failed to register {tool['name']}: {e}", file=sys.stderr)


def main():
    gw = find_existing_gateway()
    if gw:
        gateway_id = gw["gatewayId"]
        print(f"  Gateway already exists: {gateway_id}", file=sys.stderr)
    else:
        gateway_id = create_gateway()
        wait_for_gateway(gateway_id)

    gateway_url = f"https://{gateway_id}.gateway.bedrock-agentcore.{REGION}.amazonaws.com/mcp"

    print(f"  Registering targets...", file=sys.stderr)
    register_targets(gateway_id)

    # Output for shell to capture
    print(f"GATEWAY_ID={gateway_id}")
    print(f"GATEWAY_URL={gateway_url}")


if __name__ == "__main__":
    main()
