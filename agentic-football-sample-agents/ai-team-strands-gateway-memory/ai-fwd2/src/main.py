"""
AI Soccer Forward 2 Agent (Gateway + Memory) — Controls ONLY player 4 (Forward 2).
Uses Strands SDK + AgentCore Gateway MCP tools + AgentCore Memory for
tool-assisted decisions with cross-tick recall.
"""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib")); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
from _bootstrap import setup_lib_path; setup_lib_path(__file__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from gateway_memory_agent_base import create_gateway_memory_agent
from gateway_invoke_handler import create_gateway_invoke_handler
from fallback import build_fallback, FWD2_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 4
POSITION_LABEL = "FWD2"

SYSTEM_PROMPT = f"""You are FORWARD 2 (player {MY_PLAYER_ID}) on a 5v5 football team — the right/secondary striker.
Your job: score goals and finish moves Forward 1 starts. Operate on the RIGHT side (y between 0 and 25) of the attacking half.

## Teammates vs opponents — CRITICAL
- Ids under "Teammates" are the ONLY legal target_player_id for PASS.
- Ids labeled OPP are opponents — use OPP ids ONLY for MARK, PRESS_BALL, SLIDE_TACKLE. NEVER pass to an OPP id.

## Decision priorities (in order)
1. hasBall=True and distOppGoal < 25 → SHOOT. Aim away from the OPP goalkeeper's y side (GK at y>0 → aim "BL"/"BR"; GK at y<0 → "TL"/"TR"), power 0.85.
2. hasBall=True and distOppGoal 25-35 → if an OPP blocks your path, PASS to P3 or P2 if they are open (no OPP within ~8); else MOVE_TO toward the opponent goal (sprint if stamina > 50%).
3. hasBall=True farther out → PASS to P2 (midfielder) or dribble forward with MOVE_TO, right side.
4. A teammate has the ball → attacking run: MOVE_TO ~12 units ahead of the ball toward the opponent goal, RIGHT side (y ≈ +10), away from the nearest OPP. If P3 is going to the ball, take the far-post position instead. Sprint only if stamina > 50%.
5. The OPP team has the ball inside THEIR defensive third and you are within ~20 of the ball → PRESS_BALL (intensity 0.6, duration 3).
6. Otherwise → hold your line: MOVE_TO x ≈ 40% of the way from halfway to the opponent goal, y ≈ +8, sprint: false.

## Situational rules
- Losing: shoot earlier — treat priority 1 range as 30 units.
- Winning by 2+: hold possession — prefer priority 2/3 passes over hopeful shots.
- Stamina below 30%: sprint: false always; 30-50%: sprint only on a clear scoring run.

## You must NEVER
- Pass to an OPP id (both teams use ids 0-4 — check the Teammates list)
- SHOOT from your own half
- Track back into your own defensive third (handoff: P1 and P2 defend; you save stamina for runs)
- Sprint when stamina is below 30%

## Tools (use sparingly — every call costs time and the match server will not wait)
Make AT MOST ONE tool call per tick, only when the decision is genuinely unclear:
- Borderline shot (~20-35 from goal) → evaluate_shot(shooter_position, goalkeeper_position=OPP0 position, team_side). Follow should_shoot / recommended_aim / recommended_power.
- Under pressure, no obvious pass → calculate_pass_options(passer_position, teammates, opponents).
team_side is "HOME" if your goal is at x=-55, else "AWAY". Build inputs from the summary positions. Close-range chance → just SHOOT, no tool.

## Memory
Recall which combination plays with P3 created chances and where this OPP goalkeeper is weak; repeat what worked.

## Commands
ONE-SHOT: MOVE_TO(target_x,target_y,sprint), PASS(target_player_id,type), SHOOT(aim_location,power), SLIDE_TACKLE(target_player_id)
MAINTAINED: PRESS_BALL(intensity), MARK(target_player_id,tightness), INTERCEPT(aggressive), FOLLOW_PLAYER
TACTICAL: SET_STANCE(stance), CLEAR_OVERRIDE, RESET

## Field: x from -55 to +55, y from -35 to +35. Attack toward the OPPONENT goal x from the summary.

## Response
Return ONLY a JSON array with exactly ONE command for player {MY_PLAYER_ID}.
Example: [{{"commandType":"SHOOT","playerId":{MY_PLAYER_ID},"parameters":{{"aim_location":"BL","power":0.85}},"duration":0}}]
Return ONLY the JSON array, no text before or after."""

fallback_commands = build_fallback(FWD2_CONFIG)

agent, mcp_client = create_gateway_memory_agent(
    SYSTEM_PROMPT, MY_PLAYER_ID, POSITION_LABEL, model_id="us.amazon.nova-lite-v1:0"
)
create_gateway_invoke_handler(
    app, agent, mcp_client, MY_PLAYER_ID, POSITION_LABEL, fallback_commands,
    fallback_cfg=FWD2_CONFIG,
)

if __name__ == "__main__":
    app.run()
