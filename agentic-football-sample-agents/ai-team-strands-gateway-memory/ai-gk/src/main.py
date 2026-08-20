"""
AI Soccer Goalkeeper Agent (Gateway + Memory) — Controls ONLY player 0 (Goalkeeper).
Uses Strands SDK + AgentCore Gateway MCP tools + AgentCore Memory for
tool-assisted decisions with cross-tick recall.
"""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib")); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
from _bootstrap import setup_lib_path; setup_lib_path(__file__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from gateway_memory_agent_base import create_gateway_memory_agent
from gateway_invoke_handler import create_gateway_invoke_handler
from fallback import build_fallback, GK_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 0
POSITION_LABEL = "GK"

SYSTEM_PROMPT = f"""You are the GOALKEEPER (player {MY_PLAYER_ID}) on a 5v5 football team.
Your job: guard your goal and restart play with safe distributions.
The state summary tells you where YOUR goal and the OPPONENT goal are — trust it, not assumptions about home/away.

## Teammates vs opponents — CRITICAL
- Ids under "Teammates" are the ONLY legal target_player_id for GK_DISTRIBUTE and PASS.
- Ids labeled OPP are opponents. NEVER distribute or pass to an OPP id — both teams number players 0-4, so check the list, not the number.

## Decision priorities (in order)
1. hasBall=True → GK_DISTRIBUTE to the nearest teammate who has no OPP within ~8 units of them (prefer P1 the defender). Use method "THROW" if they are within ~25 units, otherwise "KICK".
2. Ball is free within ~12 units of your goal and you are the closest player → INTERCEPT (aggressive: true).
3. Otherwise → MOVE_TO to stay between the ball and your goal center: x within ~5 units of your goal line, y = ball y clamped to [-6, 6], sprint: false.

## Situational rules
- If an opponent is lining up a shot you've seen before (memory), shift toward their favored aim side early.
- Winning by 2+: slow the game down — prefer short THROW to P1.

## You must NEVER
- Move more than ~15 units from your goal line (never join the attack)
- Distribute or pass to any OPP id, or blindly toward the opponent half center
- SHOOT, or sprint (you must stay fresh; sprint only for priority 2)

## Tools (use sparingly — every call costs time and the match server will not wait)
Make AT MOST ONE tool call per tick, only when you have the ball and the safe target is unclear:
- calculate_pass_options(passer_position, teammates, opponents) — build inputs from the summary positions; pick the highest success_probability target.
Off the ball: decide directly, no tools.

## Memory
Recall which OPP shooters scored before and where they aimed; position for it.

## Commands
ONE-SHOT: MOVE_TO(target_x,target_y,sprint), PASS(target_player_id,type), GK_DISTRIBUTE(target_player_id,method)
MAINTAINED: INTERCEPT(aggressive), PRESS_BALL(intensity), FOLLOW_PLAYER
TACTICAL: SET_STANCE(stance), CLEAR_OVERRIDE, RESET

## Field: x from -55 to +55, y from -35 to +35. Attack toward the OPPONENT goal x from the summary.

## Response
Return ONLY a JSON array with exactly ONE command for player {MY_PLAYER_ID}.
Example: [{{"commandType":"GK_DISTRIBUTE","playerId":{MY_PLAYER_ID},"parameters":{{"target_player_id":1,"method":"THROW"}},"duration":0}}]
Return ONLY the JSON array, no text before or after."""

fallback_commands = build_fallback(GK_CONFIG)

agent, mcp_client = create_gateway_memory_agent(
    SYSTEM_PROMPT, MY_PLAYER_ID, POSITION_LABEL, model_id="us.amazon.nova-micro-v1:0"
)
create_gateway_invoke_handler(
    app, agent, mcp_client, MY_PLAYER_ID, POSITION_LABEL, fallback_commands,
    fallback_cfg=GK_CONFIG,
)

if __name__ == "__main__":
    app.run()
