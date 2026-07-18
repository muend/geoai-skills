# Security Policy

## Supported versions

This project is in pre-release. Security fixes are applied to the latest
version on the `main` branch only.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose data,
credentials, or unsafe agent behavior. Use GitHub's private vulnerability
reporting for this repository. Include:

- the affected skill, script, or workflow;
- the smallest reproducible example;
- the potential impact;
- any suggested mitigation.

Expect an acknowledgement within seven days. Do not include real secrets,
private geospatial datasets, or personally identifying location traces in a
report.

## Skill-specific threat model

Reviews prioritize prompt injection through untrusted data, unsafe shell or
SQL construction, credential exposure, unpinned executable dependencies,
unexpected network access, destructive file operations, and publication of
sensitive locations. A skill must not claim that an external artifact is safe
without inspecting or constraining how the agent consumes it.

