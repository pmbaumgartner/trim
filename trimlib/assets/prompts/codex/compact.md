You are performing a CONTEXT CHECKPOINT COMPACTION for a coding agent. Create a
handoff summary for another LLM that will resume the task.

This is a working-state summary, not an archive. Preserve the information
needed to continue without unnecessary re-exploration, while aggressively
dropping recoverable or superseded context.

Include:
- Current user request, acceptance criteria, and durable constraints/preferences.
- Current progress and key decisions made.
- Files modified or planned for modification: path, symbols/functions touched,
  reason, current status, and unresolved risks.
- Latest verification state: exact command, pass/fail result, and only the
  currently relevant failing assertion/error/traceback frame.
- What remains to be done as clear next steps.
- Critical data, examples, references, or output-file paths needed to continue.

Compress:
- Files only read: path + role + relevant symbols/line ranges. Do not include
  full file contents.
- Search/listing results: only discoveries that changed the plan.
- Fixed errors: one sentence only if useful to avoid repeating them.

Drop:
- Full contents of unchanged or read-only files that can be reread from disk.
- Full contents of files later edited, unless the exact snippet is the
  unresolved issue.
- Superseded logs, verbose build output, dependency listings, and redundant
  exploration.
- Verbatim conversation history, except for current requirements and durable
  user constraints.

Be concise, structured, and focused on helping the next LLM seamlessly continue
the work.
