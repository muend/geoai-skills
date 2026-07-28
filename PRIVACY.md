# Privacy Policy

Effective date: July 28, 2026

GeoAI Skills is an open-source, skills-only plugin maintained by Muhammed Enes
Duran. It provides instructions, references, and optional local scripts for AI
agents. It does not operate a hosted service, require a GeoAI Skills account,
or include maintainer-operated telemetry.

## Data handled by the plugin

The plugin itself does not automatically collect, transmit, sell, or retain
personal data. An AI runtime may process prompts, files, geospatial datasets,
credentials, or tool results that a user chooses to provide while following a
skill. That processing is performed by the selected AI runtime and any
user-selected external service, under their respective terms and privacy
policies.

Some skills describe optional integrations such as cloud geospatial services,
databases, or a local ArcGIS Pro bridge. These integrations are not operated by
GeoAI Skills. Users control whether to configure or invoke them and are
responsible for reviewing their data-handling terms.

## Local scripts and credentials

Bundled scripts are intended to run in the user's environment. They do not
contain analytics or a maintainer-controlled data endpoint. Users should keep
credentials in their runtime's supported secret store or environment
configuration and should never place secrets in prompts, issue reports, or
committed files.

## Sensitive geospatial data

Location data can reveal homes, routines, protected sites, vulnerable
populations, or critical infrastructure. Users should minimize, aggregate,
redact, or otherwise protect sensitive spatial data before sharing it with an
AI runtime or external service.

## Support and security reports

General support is available through the repository's
[GitHub Issues](https://github.com/muend/geoai-skills/issues). Do not include
secrets, private datasets, precise personal locations, or other sensitive data
in a public issue. Potential vulnerabilities should be reported through
[GitHub private vulnerability reporting](https://github.com/muend/geoai-skills/security/advisories/new)
as described in the [security policy](SECURITY.md).

## Changes

Material changes to this policy will be recorded in the public repository
history and reflected by an updated effective date.
