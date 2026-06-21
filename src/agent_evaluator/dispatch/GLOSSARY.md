# Dispatch domain — publication safety

This benchmark uses invented entities, locations, values, policies, and
scenario text. It contains only generic freight terminology required to model
equipment matching, endorsements, Hours-of-Service, availability, customer
restrictions, deadhead distance, priority, and fairness.

The source-to-public vocabulary mapping is intentionally maintained outside
this repository. Publishing that mapping would defeat the purpose of removing
source-system terminology.

`tests/test_dispatch_scrub.py` scans publishable repository text and serialized
scenario data against one-way fingerprints of restricted vocabulary. The
restricted strings themselves are not stored in this repository.

## Public modeling boundary

The benchmark deliberately excludes organization-specific identifiers,
customer data, tuned ranking formulas, earnings or allocation policies,
internal service names, and production-derived constants. Soft preferences are
reported as independent signals rather than combined into a proprietary score.
