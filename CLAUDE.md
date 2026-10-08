@AGENTS.md

## Claude Code specifics
- Installed as a plugin, the skills are namespaced (`/game-changer:mod-any-game`), the FixedSeed MCP server comes
  from `.mcp.json` (a local stdio server, `bin/fsgc fixedseed mcp`; needs `FIXEDSEED_KEY` in the environment), and a SessionStart hook puts `fsgc` on PATH.
- The MCP server's `passthrough` prompt shows up as an MCP slash command: two games in, a plan and the method out.
- In a clone, `.claude/settings.json` adds the same PATH hook and `.claude/skills` links to `skills/`.
