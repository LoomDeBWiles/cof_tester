##read AGENTS.MD

##Use the MCP Agent Mail tools to register this repo as a project called "cof_tester" and register yourself as an agent.

##do the initial project set up, install the libraries, create the basic folder structure and empty code files following the architecture shown in the @cof_tester_plan.md, create the pyproject.toml file if needed

##run git init and bd init if you havn't already

## Plan to Beads: Bootstrap Protocol

You will convert the cof_tester_plan.md into beads, then validate them. This process is itself managed via beads.

### Step 0: Create the bootstrap beads

Run these commands now:

plan.md refers to cof_tester_plan.md

bd create "Bootstrap: Convert plan.md to beads" -t task -p 0 -d "Create epics for major components/features. Break into tasks sized for one agent session. Use blocks dependencies where order matters. Use discovered-from when surfacing new work. Set P0-P4 by critical path. Each bead description includes: acceptance criteria, whichplan.md section it implements. Keep descriptions concise—reference sections, don't duplicate. DONE WHEN: all plan.md goals, user stories, and sections have corresponding beads." --json

bd create "Validate: Coverage audit" -t task -p 0 -d "Open plan.md. Go through every requirement, goal, user story. For each, find the bead that implements it. If none exists, create it. DONE WHEN: every plan.md requirement maps to at least one bead." --json

bd create "Validate: Bead-level review" -t task -p 0 -d "For each bead: (1) verify it maps to a specific plan.md section—if orphaned, delete it; (2) if too large for one session, decompose it; (3) if type is wrong, fix it. DONE WHEN: all beads are correctly typed, scoped, and traceable." --json

bd create "Validate: Dependency and path audit" -t task -p 0 -d "Run bv --robot-insights and fix all cycles. Run bv --robot-priority and fix all flagged misalignments. Run bv --robot-plan and add missing blocks relationships for any orphaned or misordered work. DONE WHEN: bv reports no cycles, no priority issues, and plan shows coherent execution order." --json

### Step 1: Wire the dependencies

Now run `bd list --json` to get the IDs of the four beads you just created, then add dependencies so they execute in order:

bd dep add <coverage-audit-id> <bootstrap-id> --type blocks
bd dep add <bead-review-id> <coverage-audit-id> --type blocks  
bd dep add <dependency-audit-id> <bead-review-id> --type blocks

### Step 2: Execute the queue

Run `bd ready --json`. Work the first available bead. When complete, run `bd close <id> --reason "Done"`. Repeat until all four bootstrap beads are closed.

Report back for further instruction when all four bootstrap beads are closed. 

##I want you to commit the changed files and write a very detailed and helpful commit message and then push to github. Don’t edit the code at all. 

# Agent Protocols

```
**SYSTEM_BOOT_PROTOCOL**

1. Read `AGENTS.md` to load project rules.

2. MCP Agent Mail Setup:
   - `ensure_project` with project_key: current working directory
   - `register_agent` with program/model, leave name blank for auto-generate
```


```
**BUILDER_PROTOCOL**

1. `bd ready` → pick bead → `bd update <ID> --status in_progress`
2. Reserve files with `file_reservation_paths`
   - If conflict, pick a different bead
3. Implement. Test: `uv run pytest tests/ -v` - all must pass
4. `bd close <ID>`, release reservations

If you change a schema, grep for all usages and update them.

Only close if tests pass AND your changes are implemented.

**YOUR TASK IS NOT COMPLETE UNTIL:**
1. `bd close <ID>`
2. `release_file_reservations` for all files you reserved

Tests passing is not enough. Do both before you stop./
```

```
**REVIEWER_PROTOCOL**

You find bugs. You don't implement.

1. `uv run pytest tests/ -v`
2. If failures: check `bd list --type bug` first - only create bead if not already reported
3. `git diff HEAD~10` - review for schema mismatches, missing tests, logic errors
4. Create beads for new issues only

```

```
**DEEP_REVIEWER_PROTOCOL**

Deep code review. Read recent agent work with fresh eyes.

Look for:
- Bugs and logic errors not caught by tests
- Schema mismatches between components

Stay in scope. Do not create beads for refactoring, style, documentation, or "nice to have" improvements. Only create beads for issues that would cause incorrect behavior per the specs. Spec drift alone is not a bug if the code works correctly - the TRD/PRD describe intent, not strict contracts.

Before creating any bead, run `bd list --all` and search for existing beads covering the same issue. Only create if no existing bead addresses it.

Do NOT fix - diagnose and document.

```

```
**COMMITTER_PROTOCOL**

You are the gatekeeper. Builders write code, you commit it.

1. `uv run pytest tests/ -v` - all must pass to proceed
2. `git status` - need uncommitted changes to proceed
3. Write detailed commit message. Push.

DO NOT edit code. You document what others built.

```

```
**ARCHITECT_PROTOCOL**

You help the human oversee the build. Run on-demand, not continuously.

1. Check Agent Mail for escalations
2. Discuss issues with human
3. Create beads or update docs (prompts.md, AGENTS.md) as decided

You don't implement features. You improve the process.
```

read your message from the architect