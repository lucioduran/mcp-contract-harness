# Contributing

Use English throughout and do not use em dash characters. Keep changes focused.
Run the checks in README before opening a pull request. Include regression tests
for changed behavior, document protocol tradeoffs outside code, and avoid claims
about untested clients or environments. Never replace inconvenient evidence.
Create a new output directory when reproducing. Update versioned results only
with an explicit explanation of the changed code, dependencies, or environment.

This repository uses local CPU resources and requires no model API. Heavy future
benchmarks must use the workspace's shared benchmark lock when operating within
the engineering evidence workspace; ordinary unit and interoperability checks
are small correctness tests. Do not commit credentials or private transcripts.
