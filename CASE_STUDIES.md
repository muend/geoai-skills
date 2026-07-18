# GeoAI failure cases

This file separates reproducible evidence from illustrative examples. Entries
must never imply real-world use unless a privacy-safe reproducer, issue, or
artifact is linked.

## Illustrative examples

The following scenarios explain the failure modes targeted by the skills. They
are not published benchmark results or verified user testimonials.

| Skill | Failure mode | Expected intervention |
|---|---|---|
| `mcda-suitability-analysis` | An AHP matrix has a consistency ratio of 0.19. | Reject the weights, identify discordant judgments, and require revision before mapping. |
| `geo-deep-learning` | Image chips are randomly split and report 0.95 validation IoU. | Reject the headline metric until spatially blocked evaluation measures geographic generalization. |

## Reproducible real-world cases

No cases have been accepted yet. Add a case through a pull request containing:

1. a dated, privacy-safe problem statement;
2. a public or synthetic minimal reproducer;
3. behavior without and with the relevant skill;
4. the verification method and artifacts;
5. limitations and environment details.

