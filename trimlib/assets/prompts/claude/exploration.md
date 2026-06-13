## Exploration best practices

Use the trim-explore subagent for broad codebase exploration, call graph
discovery, search fanout, or large read-only inspection.

Use the `trim-explorer` subagent before:

- searching across more than one directory
- inspecting call graphs, dependency chains, imports, or test fanout
- locating tests or fixtures across the repository
- reading a file likely over 300 lines
- running `grep`, `find`, `rg`, `ls`, or similar commands expected to produce
  more than 30 lines

Avoid broad grep/read fanout in the main thread unless the search is tightly
scoped. Ask trim-explorer to find exact files, symbols, and line ranges, then
read only the minimal ranges needed for editing or verification.
