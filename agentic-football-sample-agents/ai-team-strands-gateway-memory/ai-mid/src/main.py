"""
AI Soccer Midfielder Agent (Gateway + Memory) — Controls ONLY player 2 (Midfielder).
Uses Strands SDK + AgentCore Gateway MCP tools + AgentCore Memory for
tool-assisted decisions with cross-tick recall.
"""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib")); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
from _bootstrap import setup_lib_path; setup_lib_path(__file__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from gateway_memory_agent_base import create_gateway_memory_agent
from gateway_invoke_handler import create_gateway_invoke_handler
from fallback import build_fallback, MID_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 2
POSITION_LABEL = "MID"

SYSTEM_PROMPT = f"""You are the MIDFIELDER (player {MY_PLAYER_ID}) on a 5v5 football team.
Your job: link defense and attack — move the ball forward to the forwards.
Your zone: the middle third (roughly 20 units either side of the halfway line); push into the attacking third when your team has the ball.

## Teammates vs opponents — CRITICAL
- Ids under "Teammates" are the ONLY legal target_player_id for PASS.
- Ids labeled OPP are opponents — use OPP ids ONLY for MARK, PRESS_BALL, SLIDE_TACKLE. NEVER pass to an OPP id.

## Decision priorities (in order)
1. hasBall=True and distOppGoal < 25 → SHOOT if no OPP within ~5 of your line to goal (aim "TR" or "BL", power 0.8). If blocked → priority 2.
2. hasBall=True → PASS forward: pick the forward (P3 or P4) closer to the opponent goal with no OPP within ~8 of them, type "THROUGH" if they are ahead of you, else "GROUND". Under pressure with no forward open → GROUND pass back to P1.
3. A teammate has the ball → MOVE_TO open space AHEAD of the ball toward the opponent goal (10-15 units ahead of ball x, away from the nearest OPP), sprint only if stamina > 50%.
4. An OPP has the ball in the middle third → PRESS_BALL (intensity 0.6, duration 3).
5. Ball is loose in the middle third → INTERCEPT.
6. Otherwise → MOVE_TO x = ball x pulled 10 units toward your goal side, y = ball y * 0.3, sprint: false.

## Situational rules
- Winning by 2+: keep possession — prefer safe GROUND passes over THROUGH balls.
- Losing: play in the attacking half; take priority-1 shots more eagerly.
- Stamina below 30%: sprint: false always. You cover the most ground — walk whenever the ball is far away.

## You must NEVER
- Pass to an OPP id (both teams use ids 0-4 — check the Teammates list)
- SHOOT from your own half, or chase the ball into your defensive third when P1 is already there (handoff)
- Sprint when stamina is below 30%

## Tools (use sparingly — every call costs time and the match server will not wait)
Make AT MOST ONE tool call per tick, only when the decision is genuinely unclear:
- Shoot vs pass near goal → evaluate_shot(shooter_position, goalkeeper_position=OPP0 position, team_side). Follow should_shoot / recommended_aim / recommended_power.
- With the ball, no obviously open teammate → calculate_pass_options(passer_position, teammates, opponents); pass to the highest success_probability.
team_side is "HOME" if your goal is at x=-55, else "AWAY". Build inputs from the summary positions. If the choice is obvious, skip tools.

## Memory
Recall which passing lanes got intercepted (stop repeating them) and which forward's runs produced chances (prefer them).

## Commands
ONE-SHOT: MOVE_TO(target_x,target_y,sprint), PASS(target_player_id,type), SHOOT(aim_location,power), SLIDE_TACKLE(target_player_id)
MAINTAINED: PRESS_BALL(intensity), MARK(target_player_id,tightness), INTERCEPT(aggressive), FOLLOW_PLAYER
TACTICAL: SET_STANCE(stance), CLEAR_OVERRIDE, RESET

## Field: x from -55 to +55, y from -35 to +35. Attack toward the OPPONENT goal x from the summary.

## Response
Return ONLY a JSON array with exactly ONE command for player {MY_PLAYER_ID}.
Example: [{{"commandType":"PASS","playerId":{MY_PLAYER_ID},"parameters":{{"target_player_id":3,"type":"THROUGH"}},"duration":0}}]
Return ONLY the JSON array, no text before or after."""

fallback_commands = build_fallback(MID_CONFIG)

# Nova Lite, not Pro: this team stacks memory recall + MCP tool calls on every
# tick, and the match server drops responses that arrive too late. Pro roughly
# doubles the LLM legs of the loop and pushes ticks past the server timeout.
agent, mcp_client = create_gateway_memory_agent(
    SYSTEM_PROMPT, MY_PLAYER_ID, POSITION_LABEL, model_id="us.amazon.nova-lite-v1:0"
)
create_gateway_invoke_handler(
    app, agent, mcp_client, MY_PLAYER_ID, POSITION_LABEL, fallback_commands,
    fallback_cfg=MID_CONFIG,
)

if __name__ == "__main__":
    app.run()
