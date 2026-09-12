# M17 Initial Reliability SLOs

These are pilot operating targets, not contractual guarantees.

| Signal | Initial target |
| --- | --- |
| Runtime availability | >= 99.5% monthly |
| API server error rate | < 1% over 15 minutes |
| Core API p95 latency | < 750 ms under pilot load |
| Core API p99 latency | < 1500 ms under pilot load |
| `/health/ready` recovery after dependency restore | < 60 seconds |
| Outbox processing lag | < 60 seconds under pilot load |
| Backup RPO | <= 6 hours |
| Recovery RTO | <= 2 hours |
| Failed backup age | alert when > 6 hours |
| Unknown release in production | never |

## Error-budget principle

A milestone should not add capacity or features while a critical reliability
regression is unresolved.

## Cardinality policy

Metrics must not label series by:

- user ID
- student ID
- guardian ID
- institution ID
- organization ID
- raw request path with identifiers

High-cardinality or personal dimensions belong in controlled diagnostic traces,
not global metrics.
