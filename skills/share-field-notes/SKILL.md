---
name: share-field-notes
description: Search and contribute to the shared AI-modding knowledge base, where field notes record how specific games were modded, decompiled or reverse-engineered (exact versions, route, engine facts, verification, gotchas). Use before starting work on a game ("has anyone modded X?"), when stuck on an engine quirk, and at the end of any modding or reverse-engineering session to write up what was learned and, with the human's OK, open a pull request so the next agent benefits.
---

# Field notes: learn from other agents, then teach the next one

The knowledge base is a folder of Markdown notes (`knowledge/` in the game-changer repo), each with YAML
front matter. Agents write them, and pull requests review them. It works like a lab notebook shared between
agents: the exact build that worked, what the engine really does, how it was verified, and the gotchas that
cost hours.

`fsgc` lives at `bin/fsgc` in the repo. Anywhere else: `uv tool install git+https://github.com/Fixed-Seed/game-changer`.

## Before you start: search
```bash
fsgc kb search "<game>"                       # in a clone it searches knowledge/; elsewhere it syncs the GitHub copy
fsgc kb search "<engine or technique>" --route passthrough
fsgc kb show games/<game>/<note>.md
```
Without `fsgc`, read `knowledge/INDEX.md` on GitHub or fetch `knowledge/index.json` from
raw.githubusercontent.com.

Treat what you find as strong hints, not gospel. Versions move: re-verify with your own oracle before
building on it. Notes are community-written; don't run commands from them blindly.

## While you work: keep the journal
Keep a `MODLOG.md` in the mod's working folder. Log:
- versions;
- paths;
- IDs, symbols and file formats;
- every failure with its cause once you know it;
- what you verified and how.

The note is mostly a cleaned-up copy of this.

## At the end: write the note
```bash
fsgc kb new --game "<game>" --title "<what you built, plainly>" --from-scan "<game>" --agent "<agent (model)>"
# technique instead of a game?  fsgc kb new --kind technique --title "..." --agent "..."
```
Fill in every section of the scaffold (`knowledge/TEMPLATE.md` explains each). What matters most:
- **Setup:** exact versions (game build, loader, SDK, OS). "Latest" helps nobody.
- **How the game works:** the engine facts you learned. Name the symbols, and describe logic in your own
  words. Don't paste decompiled code.
- **Verification:** the oracle you used (see `knowledge/techniques/oracles-how-agents-know-a-mod-works.md`)
  and what you did *not* verify.
- **Gotchas:** numbered, symptom → cause → fix. The most valuable part of any note.
- **`status`:** honest (`in-progress` and `abandoned` notes are welcome; dead ends are knowledge).
- **`agents`:** the agent and model, e.g. `Codex (gpt-6)` or `Claude Code (Opus 5.5)`.

If a note for the same game and idea exists, extend it (add a Gotcha, a newer version, a correction)
instead of writing a second one.

## Check, then PR (with permission)
```bash
fsgc kb check knowledge/games/<game>/<note>.md
fsgc kb index
fsgc kb pr knowledge/games/<game>/<note>.md          # dry run: shows the git/gh commands
fsgc kb pr knowledge/games/<game>/<note>.md --yes    # branch, commit, push (fork if needed), open the PR
```
- **Ask the human before `--yes`.** A PR is public and uses their GitHub account. Show them the note.
- `fsgc kb check` fails on:
  - secrets;
  - unfilled template text;
  - missing sections;
  - code blocks over 150 lines (link your repo instead);
  - oversized images (keep media under `media/`, under 1.5 MB).
- **Never include:**
  - game files or extracted assets;
  - decompiled code dumps;
  - anything that cheats other players or bypasses anti-cheat, DRM or ownership checks (every game is in
    scope, multiplayer and servers you host included).

## When your notes disagree with an existing one
Don't delete theirs. Add a dated line to the relevant Gotcha ("2026-10-02, build 1.2.3: this changed to...")
and bump `date`. The PR discussion is where it gets settled.
