# Data Lineage

Every analytical output must be traceable backward to original source documents.

## Lineage chain

```text
SOURCE DOCUMENT
      ↓
EXTRACTED VALUE/TEXT
      ↓
NORMALIZED FACT / EVIDENCE
      ↓
CALCULATION
      ↓
CLAIM
      ↓
VERIFICATION
      ↓
REPORT
```

## Example

Claim: "Revenue grew 12.4% YoY"

Trace:

```text
report.claim_42
  ↓ calculation_123
  ↓ fact_2026_q2, fact_2025_q2
  ↓ document A page 4, document B page 4
```

## Report output types

Final reports distinguish:

- **FACT** — directly extracted or normalized from source
- **CALCULATION** — deterministic computation over facts
- **MANAGEMENT EXPLANATION** — attributed management commentary
- **OBSERVATION** — pattern noted from facts/evidence
- **INTERPRETATION** — analyst inference (must not be presented as fact)

The system must not silently convert observations into causal conclusions.

## Source tiers

| Tier | Description | Usage |
|------|-------------|-------|
| A | Original issuer/regulator documents | Primary evidence |
| B | Structured exchange metadata | Supporting metadata |
| C | Third-party summaries | Must not replace Tier A where Tier A exists |

## Preservation requirements

Original source artifacts retain:

- original filename
- download timestamp
- publication timestamp
- SHA256 hash
- company association
- document type
- original bytes in object storage

## Database access

Business code uses repositories in `src/db/repositories/`. Raw SQL stays inside the data-access layer unless performance requires otherwise and ownership is explicit.

## Verification linkage

Verified claims reference:

- supporting facts and/or calculations
- documentary evidence spans (page, section, chunk)
- verification method and status

Unverified claims must not appear in final research reports.
