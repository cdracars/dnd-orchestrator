# ⚔️ Dungeon Master's Orchestrator

A local-network command center for running D&D. One server, every device at the table
(phones, tablets, laptops) sees the same dice rolls, initiative tracker and Archive live.

## Run it
```bash
./run.sh          # creates a venv, installs deps, starts the server
```
It prints a `Table:` URL (e.g. `http://192.168.1.50:8080`). Open it on any device on your Wi-Fi.

For full natural-language orchestration (Claude plans and chains tools):
```bash
cp .env.example .env     # then put your ANTHROPIC_API_KEY in it
```
Without a key it still works in **offline Rules Engine mode** with direct commands:
`roll 4d6kh3`, `encounter level 5 party of 4 hard undead`, `character level 3 tiefling warlock`,
`npc innkeeper`, `loot level 6 hoard`, `start combat`, `next turn`, `note: title - text`,
`party`, `add <hero> to the party`, `remove <hero> from the party`.

## What's inside
| Piece | What it does |
|---|---|
| **Orchestrator** (`agent.py`) | Claude tool-calling loop; chains tools for requests like "prep tonight's session" |
| **Rules Sage** | Rules-legal 5e characters (all 12 classes, 9 races, levels 1-20, slots, saves, skills) |
| **Encounter Forge** | DMG XP-budget math (multipliers, party size) over a themed monster list |
| **Tavern Keeper** | NPCs with a want, a secret, a voice and an attitude |
| **Hoard Keeper** | Treasure by tier, gems, magic items by rarity |
| **Dice Goblin** | `NdM+K`, keep-highest, advantage/disadvantage, shared roll feed |
| **War Table** | Initiative, HP bars, conditions, turn/round tracking for the **party** (a roster separate from the Archive) |
| **Print Forge** | 3D print queue; set `PRINT_WEBHOOK_URL` to POST each job to your slicer/printer orchestrator when it is queued and on every status change |
| **The Scribe** | Notes + campaign state, all in SQLite (`campaign.db`) |

All math lives in deterministic code (`engine.py`); the LLM only does narrative and routing.

## Print webhook payload
```json
{"type":"print","id":3,"name":"Goblin x3","item_type":"miniature","source_id":2,"scale_mm":28,"quantity":1,"notes":"","status":"queued"}
```

## Extending
Add a function to `tools.py`, register it in `TOOLS`, `TOOL_AGENT` and `TOOL_SCHEMAS`.
It instantly becomes available to Claude, the REST API (`POST /api/tool/<name>`) and the UI.
Run `python test_smoke.py` after changes.

## Notes
- Monster/class data is a compact SRD-style set, not the full Monster Manual. Extend `MONSTERS` in `engine.py`.
- No auth: it's meant for your home network. Don't expose the port to the internet.

## Credits
- **Juan Pablo** ([Luma-Isla Studios](https://luma-isla.com)): original author.
- **Cody Dracars**: editor and co-author.
