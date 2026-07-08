# Changelog

All notable changes to the `llnate` CLI are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-07-08

### Added

- `llnate init` scaffolds `AGENTS.md` (runtime contract, the `{question}`
  input convention, guardrails, local-verify loop, and a full `llnate` CLI
  reference) plus a thin `CLAUDE.md` that points coding assistants at it.
  `llnate plugin install` writes the same `CLAUDE.md` pointer.
- `llnate keys` now commits `keys.env`/`.sops.yaml` and runs `push` right
  after encrypting, so wiring credentials flows straight into a deploy. The
  Ready summary (`push`/`status`) also prints a ready-to-run `curl` example
  against `/kickoff` and a `claude mcp add` command for the deployed agent.

### Changed

- `pyproject.toml` now reads its version from `llnate/__init__.py:__version__`
  (`dynamic = ["version"]` via `[tool.hatch.version]`) instead of pinning its
  own copy, so the two can no longer drift out of sync.
- Default API URL moved to `https://api.layernetes.learninglayer.ai` (from
  `https://api.learninglayer.ai`).
- Package metadata: licensed AGPL-3.0-or-later, authored by Sanscourier.ai.

### Fixed

- `llnate push` no longer ends early on a stale status left over from the
  previous revision. It now waits for the reported `sha` to match the one it
  just pushed before trusting `phase`/`url` (falling back to the old
  grace-window behavior against a legacy `ll-api` that doesn't report a
  `sha`).
- Scaffolded `crew.py` normalizes arbitrary caller payloads to a non-empty
  `question`, so off-key MCP/HTTP inputs no longer crash with "Missing
  required template variable".

## [0.1.0] - 2026-07-04

### Added

- Initial release of the `llnate` developer CLI: `init` (CrewAI scaffold,
  Dockerfile, CI workflow that pre-pulls the base image and writes registry
  auth), `plugin install`, `login` (provisions repo + keys, wires the git
  remote), `keys` (sops/age encryption, no plaintext left on disk), `push`
  (streams phase transitions), `status`, and `delete`.
