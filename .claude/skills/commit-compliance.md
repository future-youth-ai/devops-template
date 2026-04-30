---
name: commit-compliance
description: >
  Enforces the future-youth-ai commit message format before committing.
  Use this skill whenever you are about to create a git commit, write a
  commit message, or the user asks to commit changes. Also triggers when
  the user runs /commit or asks you to "commit", "push", "save changes",
  or any variation. The skill validates commit messages against the
  project's CI-enforced rules so violations are caught locally instead of
  failing in CI. If you are writing a commit message for this repo, you
  MUST follow these rules.
---

# Commit Compliance

This repo enforces strict commit message formats via CI (`commit-lint.yml`
runs `scripts/commit_lint.py` on every PR). Non-compliant commits will
block merge. This skill ensures every commit message you write passes
before it reaches CI.

## Why this matters

Commit messages are not just labels — they drive automation:
- `[DEL-xx]` and `[PHASE-x]` commits trigger Feishu Bitable sync and
  group notifications via `feishu-sync.yml`
- `[TASK-xxx]` / `[DONE-TASK-xxx]` tags update task status in Feishu
- Conventional commit types are parsed for changelogs and PR labels

A bad commit message means broken automation, not just a style violation.

## Allowed formats

Every commit subject (first line) must match **exactly one** of these
patterns. No exceptions.

### 1. Deliverable — `[DEL-xx] description`

Marks completion of a numbered deliverable. Triggers Feishu sync.

```
[DEL-04] PDF parser v1.0 complete
[DEL-12] webhook signature verification
```

### 2. Milestone — `[DEL-xx][TAG] description`

A deliverable that also hits a milestone. TAG is uppercase letters/digits
(e.g., MVP, UAT, V2). Triggers enhanced Feishu notification.

```
[DEL-07][MVP] AI review engine end-to-end runnable
[DEL-15][UAT] user acceptance tests all passing
```

### 3. Phase — `[PHASE-x] description`

Marks completion of an entire phase. Triggers Feishu phase notification.

```
[PHASE-1] Phase 1 all deliverables complete
[PHASE-3] integration testing done
```

### 4. Conventional commit — `type: description` or `type(scope): description`

For regular development work. The type must be one of:

`feat` `fix` `docs` `style` `refactor` `perf` `test` `chore` `build` `ci` `revert`

Scope is optional, in parentheses. A `!` before `:` marks breaking changes.

```
feat(meeting_bot): add minutes fallback endpoint
fix: correct timezone handling in due_date
docs: update deployment guide
ci: add scripts lint to CI gate
refactor(feishu): extract token caching
chore: bump dependencies
```

### 5. Merge / Revert (auto-generated)

GitHub-generated merge and revert commits are automatically allowed:

```
Merge branch 'feature/xxx' into dev
Merge pull request #25 from org/branch
Revert "feat: something"
```

## Optional trailing task tags

Any of the above formats can have `[TASK-xxx]` or `[DONE-TASK-xxx]`
appended at the end. These trigger Feishu task status updates.

- `[TASK-xxx]` — marks task as "in progress"
- `[DONE-TASK-xxx]` — marks task as "completed"

```
feat(api): implement login [TASK-rec123]
fix: correct timezone bug [DONE-TASK-rec456]
[DEL-04] parser complete [DONE-TASK-rec789]
```

## Validation rules (summary)

```
ALLOWED = (
    /^\[DEL-\d+\](?:\[[A-Z][A-Z0-9_-]*\])?\s+\S.*/   # deliverable/milestone
    /^\[PHASE-\d+\]\s+\S.*/                             # phase
    /^(feat|fix|docs|style|refactor|perf|test|chore|build|ci|revert)(\([\w\-./]+\))?!?:\s+\S.*/
    /^Merge (branch|pull request|remote-tracking).*/     # auto merge
)
OPTIONAL_SUFFIX = /\s*\[(?:DONE-)?TASK-[A-Za-z0-9_-]+\]\s*$/
```

The subject is validated after stripping any trailing task tag.

## Before writing a commit message

1. Determine the type of change:
   - Completing a deliverable? Use `[DEL-xx]`
   - Hitting a milestone? Use `[DEL-xx][TAG]`
   - Completing a phase? Use `[PHASE-x]`
   - Regular work? Use conventional `type: description`
2. Write the description — it must be non-empty and start with a
   non-whitespace character
3. If there's a related task in Feishu, append `[TASK-xxx]` or
   `[DONE-TASK-xxx]`
4. Verify the message matches one of the patterns above

## Common mistakes and fixes

| Wrong | Why | Fix |
|-------|-----|-----|
| `added login feature` | No type prefix | `feat: add login feature` |
| `feat:add login` | Missing space after colon | `feat: add login` |
| `Feature: add login` | Wrong case | `feat: add login` |
| `[DEL-4] parser` | Single digit OK, but verify DEL number exists | `[DEL-04] parser` (if 04 is the real number) |
| `[del-04] parser` | Lowercase DEL | `[DEL-04] parser` |
| `[PHASE-1]` | Missing description | `[PHASE-1] all deliverables complete` |
| `update: fix bug` | `update` is not a valid type | `fix: fix bug` |
| `wip: stuff` | `wip` is not a valid type | `chore: work in progress on X` |

## Integration with CI

This skill mirrors the exact same rules enforced by:
- **CI**: `.github/workflows/commit-lint.yml` runs `scripts/commit_lint.py`
- **Branch protection**: `Commit Lint` is a required check for merge to main

If a message passes this skill's rules, it will pass CI. If it doesn't
pass these rules, CI **will** reject it.
