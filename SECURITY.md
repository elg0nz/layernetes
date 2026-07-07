# Security Policy

Layernetes handles credentials by design (age keys, sops-encrypted secrets,
Gitea tokens), so security reports get priority attention.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Instead, use
GitHub's private vulnerability reporting on this repository
(Security → Report a vulnerability), or email Sanscourier.ai at
<business@sanscourier.ai>.

Include what you can: affected component (`llnate`, `ll-api`, `ll-operator`,
`llagent-base`, `ll-infra`), reproduction steps, and impact. You should hear
back within a few days.

## Scope notes

- The security-critical contract is described in the README: agent
  credentials are decrypted **in-memory only** via `sops exec-env` — plaintext
  must never reach the repo, a rendered Secret, etcd, or disk. Anything that
  breaks that property is a vulnerability.
- The Helm chart intentionally ships **no default credentials**; installs
  fail until an admin password and runner token are set. A path that lets a
  deployment come up with guessable credentials is a vulnerability.
- Local development setups (`values-local.yaml`, sslip.io hostnames, the
  documented `layernetes-local-dev` password) are explicitly out of scope —
  they are for laptops, not the internet.
