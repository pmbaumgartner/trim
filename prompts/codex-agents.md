## Context budget

For broad codebase exploration, call graph discovery, or large read-only
inspection, spawn an explorer subagent and ask it to return only relevant files,
symbols, line ranges, evidence, and recommended next read/edit.

Avoid broad grep/read fanout in the main thread unless the search is tightly
scoped.

When compacting, keep a working-state summary rather than an archive. Do not
preserve full read-only file contents or superseded logs.
