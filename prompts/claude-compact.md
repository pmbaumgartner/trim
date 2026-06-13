# Compact instructions

When compacting, optimize for continuing the active coding task, not archiving
the transcript.

Target a compact working-state summary. Prefer fewer tokens unless preserving
more detail will clearly avoid extra turns.

Preserve:
- The current user request, acceptance criteria, and durable user constraints.
- The active subtask and the next concrete action.
- Files edited or intended to be edited: path, symbols/functions touched,
  reason for change, current status, and unresolved risks.
- The current diff or patch plan only when it is not recoverable from disk or is
  needed to understand an unfinished edit.
- Latest verification state: exact command, pass/fail result, and only the
  currently relevant failing assertion/error/traceback frame.
- Architectural/API/schema decisions and why they constrain the remaining work.
- Paths to any large outputs saved by trim, if those outputs may need to be
  reopened.

Compress:
- Files that were only read: path + role + relevant symbols/line ranges. Do not
  include full file contents.
- Search, grep, glob, ls, and directory results: only the discoveries that
  affected the plan.
- Fixed errors: one sentence only if remembering them prevents repeating the
  same mistake.
- Earlier user messages: summarize durable constraints and requirement changes;
  do not preserve the transcript verbatim.

Drop:
- Full contents of unchanged files or files that can be reread from disk.
- Full contents of files later edited, unless the exact snippet is the
  unresolved issue.
- Superseded test logs, build logs, dependency listings, and repeated command
  output.
- Redundant exploration that did not affect the current plan.

If something may be needed later but is recoverable, preserve a re-read pointer
instead of the content.
