# Authoritative sources

- Last verified: 2026-07-19
- Review cadence: every 3 months
- Refresh triggers: Python packaging, pytest, GitHub Actions, or supported runtime change

## Canonical sources

- [Python Packaging User Guide](https://packaging.python.org/en/latest/) — environments, package metadata, builds, and dependency practice.
- [pytest documentation](https://docs.pytest.org/en/stable/) — test discovery, fixtures, and configuration.
- [GitHub Actions documentation](https://docs.github.com/en/actions) — workflow syntax, security, artifacts, and runners.
- [OpenSSF Scorecard documentation](https://scorecard.dev/) — repository security posture checks.

Pin production dependencies and CI actions by immutable version where practical. Revalidate operating-system matrices and supply-chain controls after platform changes.
