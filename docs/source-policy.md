# Source Policy

Policy for ingesting and using financial source documents in the MVP.

## MVP scope

MVP supports ordinary non-financial listed companies. Initial development tickers:

- FPT
- MWG
- VNM
- HPG
- VIC

## Approved source categories

| Source | Examples | Priority |
|--------|----------|----------|
| HOSE disclosures | periodic reports, event disclosures | Tier A |
| HNX disclosures | periodic reports, event disclosures | Tier A |
| SSC filings | regulator submissions | Tier A |
| Issuer IR pages | investor relations PDFs | Tier A when official |

## Ingestion rules

1. Store original bytes unchanged in object storage.
2. Record publication timestamp when available; otherwise record discovery timestamp and mark uncertainty.
3. Compute SHA256 for deduplication.
4. Resolve document versions explicitly; never overwrite prior versions silently.
5. Track each ingestion run with status and error details.

## Point-in-time enforcement

Every research run specifies `as_of`. Source selection filters:

```text
document.publication_timestamp <= research.as_of
```

If a corrected filing exists after `as_of`, the earlier version valid at `as_of` must be used.

This applies to:

- document retrieval
- financial fact selection
- corporate event inclusion
- verification evidence
- report citations

## Prohibited practices

- Silently correcting financial values extracted from source documents
- Deleting original source data
- Using Tier C summaries when Tier A originals are available
- Using documents published after `as_of`
- Allowing LLM-generated numbers without numeric verification against structured facts

## OCR and parsing fallback

When digital extraction fails:

1. Attempt alternate digital parsers.
2. Fall back to OCR with confidence scoring.
3. Mark low-confidence extractions for human review.
4. Never promote unverified OCR values to verified facts.

## Retention

Original source objects and metadata are retained for audit. Derived artifacts (chunks, embeddings, calculations) reference stable source identifiers.

## Change control

Changes to source priority, allowed domains, or point-in-time rules require an ADR in `docs/decisions/` and human reviewer approval.
