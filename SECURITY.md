# Security Policy

Luve is an early-stage, actively developed project. We take security seriously
and appreciate responsible disclosure.

## Reporting a vulnerability

Please report security issues **privately**, not through public issues:

- Open a private [GitHub security advisory](https://github.com/montyfinn/luve/security/advisories/new), or
- Contact the maintainer via the address on their GitHub profile.

Include steps to reproduce and the affected service/component (`core-api`,
`media-server`, `grading-worker`, or `infrastructure`). We will acknowledge your
report as soon as we reasonably can and coordinate a fix and disclosure timeline
with you.

## Secrets and configuration

- Real secrets live only in local `.env` files, which are **git-ignored** and
  must never be committed. Only `.env.example` templates are tracked.
- If you believe a secret was committed, treat it as compromised: rotate it
  immediately and notify the maintainer.

## Supported versions

The project does not yet publish versioned releases. Security fixes target the
`main` branch.
