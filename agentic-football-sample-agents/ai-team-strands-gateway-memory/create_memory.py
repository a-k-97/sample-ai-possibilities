"""One-time script to create an AgentCore Memory resource for the gateway+memory team.

Creates a short-term memory (STM) resource for cross-tick recall.
No long-term strategies are defined — raw events are retained for the
duration of the match session only.

The name is distinct from the memory-only team's "AITeamMatchMemory" so the
two teams never share (or steal) each other's resource when deployed into
the same account via the legacy flow.

Usage:
    AWS_DEFAULT_REGION=us-east-1 python3 create_memory.py

Prints the MEMORY_ID to stdout. Export it before deploying agents:
    export MEMORY_ID=<printed-id>
"""

import os
from bedrock_agentcore.memory import MemoryClient

MEMORY_NAME = "AITeamGwMemMatchMemory"

region = os.environ.get("AWS_DEFAULT_REGION")
if not region:
    raise RuntimeError("AWS_DEFAULT_REGION environment variable is required")

client = MemoryClient(region_name=region)

# Check if memory already exists
existing = client.list_memories()
for mem in existing:
    mem_id = mem.get("id") or mem.get("memoryId", "")
    mem_name = mem.get("name", "")
    if mem_name == MEMORY_NAME or mem_id.startswith(MEMORY_NAME):
        memory_id = mem_id
        print(f"Memory resource ready: {memory_id}")
        print(f"Export it:  export MEMORY_ID={memory_id}")
        exit(0)

# Create new memory (handle "already exists" gracefully)
try:
    memory = client.create_memory(
        name=MEMORY_NAME,
        description="Short-term memory for AI soccer gateway+memory team agents — persists game tick history within a match",
    )
    memory_id = memory.get("id") or memory.get("memoryId")
except Exception as e:
    if "already exists" in str(e):
        # Memory exists but list didn't find it — re-list and search
        existing = client.list_memories()
        for mem in existing:
            name = mem.get("name", "")
            if name == MEMORY_NAME:
                memory_id = mem.get("id") or mem.get("memoryId")
                break
        else:
            # Last resort: parse the error or use name as ID
            raise RuntimeError(f"Memory '{MEMORY_NAME}' exists but could not retrieve ID: {e}")
    else:
        raise

print(f"Memory resource ready: {memory_id}")
print(f"Export it:  export MEMORY_ID={memory_id}")
