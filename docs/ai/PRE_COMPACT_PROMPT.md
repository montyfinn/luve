# PRE_COMPACT_PROMPT.md

Copy-paste prompt này trước khi dùng `/compact`:

```text
Before compacting, create a concise but complete handoff summary.

Include:
1. Original goal
2. Current task status
3. Validated conclusions — only things proven by reading code, running commands, tests, logs, DB queries, browser automation, or user-provided evidence
4. Important files inspected or changed, with why each matters
5. Bugs found and suspected root causes
6. Changes already made
7. Important git checkpoints/commits:
   - commit hash
   - commit message
   - files included
   - what was verified before/after the commit
8. Current git worktree state:
   - committed scope
   - staged files
   - unstaged modified files grouped by likely task
   - untracked files grouped by likely task
   - files that must NOT be accidentally staged/committed
9. Remaining steps, ordered by priority
10. Constraints / things not to change
11. Operational traps discovered — environment issues, wrong assumptions, broken commands, path problems, API quirks, capacity limits
12. Exact commands, endpoints, env vars, ports, model settings, IDs, token handling rules, and session IDs that materially matter

Security rules:
- Do NOT include real secret values.
- Redact passwords, DATABASE_URL values with credentials, API keys, access tokens, refresh tokens, bearer tokens, JWTs, cookies, login payload secrets, private credentials, and production-only identifiers.
- Use placeholders like <DATABASE_URL>, <DB_USER>, <DB_PASSWORD>, <JWT_TOKEN>, <BEARER_TOKEN>, <API_KEY>, <COOKIE>, <SESSION_ID>.
- Keep real session IDs only if they are materially needed for debugging; otherwise redact them.

Then include:
13. What still needs real-world verification vs what is already proven
14. Recommended next prompt after /compact

Keep it factual.
Do not include speculation unless clearly marked as unverified.
Do not restate long logs verbatim; summarize them and keep only exact lines or IDs that materially matter.
Do not include unrelated conversation history.
```

 After compact, do not modify, stage, or commit anything until the handoff summary has been reviewed and the current git status is checked.

