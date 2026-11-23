# Start an optional GeoAI workflow

1. Install the exact supported skills separately, then preview the addon install.
2. Begin a new Codex/Claude session in the target project. Ask:
   "Read .geoai-agent-kit/START.md and COMMON.md. Act as the GeoAI coordinator
   for this task, using the defined specialist and reviewer agents when required."
3. The main session owns coordination. Read the coordinator entry in roles.json;
   do not delegate to a second coordinator.
4. Read installation.json, verify the skills_root, and create a task record using
   schemas/records.schema.json. Run the plan command. Load only selected skills.
5. Create output files and an artifacts record. Delegate the required reviews
   with original evidence and exact file hashes. Write independent review records.
6. Run deliver with the task, artifacts and reviews. Repair at most twice, then
   report remaining findings. Record failures locally for a later, explicitly
   requested skill-maintenance session.

Commands (paths are relative to the project):
```text
python .geoai-agent-kit/geoai_agents.py plan task.json
python .geoai-agent-kit/geoai_agents.py check walkability --root evidence --spec evidence/route-check.json
python .geoai-agent-kit/geoai_agents.py legacy -- --json units buffer --crs EPSG:4326 --value 500
python .geoai-agent-kit/geoai_agents.py validate-record review.json
python .geoai-agent-kit/geoai_agents.py deliver --task task.json --artifacts artifacts.json --review review.json --root output
```

Tool capabilities differ by host. Do not invent a skill invocation if the host
does not support it; follow each skill's restrictions and report missing capability.
Do not load this workflow in the historical benchmark baseline.
