# Security policy

PhishGuard stores staff personal data and phishing evidence, so security reports
are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability
reporting ("Security" tab → "Report a vulnerability") with:

- the affected version or commit,
- steps to reproduce, and
- the impact you observed.

You'll get an acknowledgement within 5 working days. Fixes are released as
soon as practical, and reporters are credited in the changelog unless they
prefer otherwise.

## Supported versions

Only the latest release on `main` receives security fixes.

## Scope

In scope: the PhishGuard application, its Docker images and deployment files.
Out of scope: findings that require an already-compromised admin account or
server, and misuse of the tool against people without authorisation (see the
Ethics section of the README).

## Hardening reference

See the Security section of the [README](README.md) and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the controls in place and the
recommended production setup.
