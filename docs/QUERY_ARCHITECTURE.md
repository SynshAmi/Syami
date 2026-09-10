# Syami Query Architecture

## 1. Purpose

Syami search is a **memory-oriented file retrieval system**.

A user's search input is treated as a fragment of memory about a file, not necessarily as a precise database query.

The user may remember:

- the exact filename or path
- an exact phrase from the content
- what the file was about
- metadata such as file type, size, or when it was modified
- some combination of the above
- metadata incorrectly or with uncertainty

The retrieval system therefore uses the evidence the user actually provides and does not force every query through the same retrieval mechanism.

---

## 2. Core Retrieval Evidence Families

There are three conceptual evidence families.

### 2.1 Identity evidence

Identity is the strongest form of lexical evidence when the user appears to be naming a specific file.

Identity includes:

- exact normalized full path
- exact normalized filename
- exact normalized stem
- exact/boundary identifier sequences where applicable

Identity is **not an RRF channel**.

Identity is evaluated separately and can establish an identity tier that influences final ordering.

Identity priority must be **query-aware**.

For example:

- a query containing a path is path-oriented
- a query containing `report.pdf` is filename-oriented
- a query containing a distinctive stem is stem-oriented

The system must not blindly assume:

`path > filename > stem`

for every query.

---

### 2.2 Topical evidence

Topical retrieval consists of four channels:

1. Title BM25 / FTS
2. Content BM25 / FTS
3. Title vector search
4. Content vector search

These are document-level retrieval channels.

Content retrieval initially happens at chunk level and is converted to document-level evidence using MaxP.

---

### 2.3 Metadata evidence

Metadata is structured evidence.

V1 metadata fields include:

- extension / document type
- modified time
- created time
- any file time where appropriate
- path prefix / path segment
- exact or ranged size

Metadata is not an RRF channel.

Metadata is used for:

- mandatory eligibility
- strict-preferred retrieval
- soft ranking influence
- deterministic explanations

---

# 3. End-to-End Query Flow

```text
User query
   ↓
Normalize
   ↓
Deterministic query planning
   ↓
SearchQueryPlan
   ├── identity probes
   ├── metadata predicates
   ├── topical text
   ├── semantic text
   ├── quoted phrases
   ├── mode / implied sort
   └── diagnostics
   ↓
Mandatory eligibility
   ↓
Identity lookup ───────────────┐
                               │
Title BM25 ────────────────────┤
Content BM25 → MaxP ───────────┤
Title Vector ──────────────────┤→ RRF → Metadata adjustment
Content Vector → MaxP ─────────┤
                               │
Metadata strict/relaxed lanes ─┘
   ↓
Identity-aware final ordering
   ↓
SQLite hydration
   ↓
Evidence + deterministic explanation
   ↓
SearchResult
```

---

# 4. Query Planning

Query planning is deterministic and conservative.

There is no LLM gatekeeper in V1.

The planner performs bounded interpretation:

1. normalize the input
2. remove command/scaffolding language where safely recognizable
3. identify literal and identity spans
4. identify hedging/scoping language
5. extract metadata predicates
6. produce topical text
7. produce semantic text
8. determine mode / implied sort
9. record diagnostics

The planner must never invent facts that are not supported by the query.

---

# 5. SearchQueryPlan

The application search layer should work from an explicit query-plan object.

Conceptually:

```text
SearchQueryPlan
├── original_text
├── normalized_text
├── topical_text
├── semantic_text
├── quoted_phrases[]
├── identity_probes[]
├── metadata_predicates[]
├── mode
├── implied_sort
└── diagnostics[]
```

The plan is the contract between query interpretation and retrieval execution.

---

# 6. IdentityProbe

An identity probe contains:

```text
raw value
normalized value
kind
source span
specificity
origin
```

Kinds include:

- PATH
- FILENAME
- STEM
- IDENTIFIER_SEQUENCE

Identity matching uses normalized equality where appropriate.

Normalization should include:

- Unicode NFKC normalization
- case folding
- whitespace normalization
- path separator normalization
- stem normalization that treats spaces, underscores, hyphens and dots consistently where appropriate

Identity must not become arbitrary substring search across the entire corpus.

---

# 7. Metadata Predicates

A metadata predicate conceptually contains:

```text
field
operator
canonical value
source span
confidence
enforcement
precision
match function
```

Confidence is a deterministic classification, not a probability.

### Confidence classes

**HIGH**

Explicit, restrictive information.

Examples:

- `only PDFs`
- `PDFs modified last week`

**MEDIUM**

Likely but not necessarily restrictive.

Examples:

- `PDF about Kalman filters`
- `presentation about transformers`

**LOW**

Explicitly uncertain or inferred.

Examples:

- `I think it was a Word document`
- `maybe a PDF`

---

# 8. Enforcement Classes

Metadata confidence and enforcement are related but distinct.

### MANDATORY

Used when the user explicitly requires the condition or when system eligibility requires it.

Example:

`only PDFs`

### STRICT_PREFERRED

Used for precise, unhedged remembered metadata.

Example:

`the PDF I modified last week`

The strict lane is attempted, but the system must also execute a relaxed lane so incorrect memory does not hide the correct file.

### SOFT_ONLY

Used for hedged, fuzzy, inferred or otherwise uncertain metadata.

It does not filter candidates.

It influences ranking/evidence only.

---

# 9. Query Confidence vs Evidence Strength

These concepts must remain separate.

### Query confidence

How strongly the system believes that a particular interpretation was actually expressed by the user.

Example:

`I think it was a Word document`

The Word-document metadata clue has low query confidence.

### Evidence strength

How strongly the retrieved data supports a match.

A PDF could have much stronger content/title evidence than the Word-document hint.

Therefore:

> A weakly remembered clue must not overpower strong retrieval evidence merely because it is a metadata field.

The implementation must represent these separately.

---

# 10. Channel Activation

If topical text exists, all four topical channels are eligible:

- title BM25
- content BM25
- title vector
- content vector

The planner does not disable a retrieval family simply because another family appears more likely.

A channel may fail during execution; failure handling is separate from planning.

---

# 11. Lexical Retrieval

Lexical retrieval uses LanceDB FTS/BM25.

### Title lexical

Search the `documents.title` field.

### Content lexical

Search the `chunks.text` field.

Quoted phrases may be used to improve exact lexical matching, but exact phrase verification must remain safe.

Do not turn ordinary topical phrases into identity matches.

Do not construct aggressive AND queries that can unnecessarily eliminate valid results.

---

# 12. Semantic Retrieval

Semantic retrieval uses the existing normalized `all-MiniLM-L6-v2` embedding model.

The same model must be used for indexed content and search queries.

Current dimensions:

```text
384
```

Vectors are normalized.

V1 should expose an explicit query embedding boundary such as:

```text
embed_query(query)
```

without changing the model or embedding/index contract.

---

# 13. Metadata Retrieval Lanes

Metadata handling uses two lanes.

Let:

- `U` = mandatory system/query eligibility
- `H` = strict-preferred predicates

### Relaxed lane

Retrieve under:

```text
U
```

This lane always runs.

### Strict lane

When strict-preferred predicates exist, also retrieve under:

```text
U ∧ H
```

This lane exists to give precise remembered metadata a useful retrieval path without making incorrect memory fatal.

The relaxed lane must not be used only as a zero-result fallback.

Both lanes should normally be evaluated.

---

# 14. Candidate Generation

Initial V1 candidate budgets are implementation parameters, not immutable truths.

Proposed starting values:

- Identity: up to 25 documents
- Metadata candidates: up to 100 documents
- Title BM25: 50 documents
- Content BM25: start at 200 chunks, expand toward 400 when document diversity is insufficient
- Title vector: 50 documents
- Content vector: start at 200 chunks, expand toward 400 when document diversity is insufficient

These numbers must be evaluated against the fixed retrieval evaluation set before being considered final.

---

# 15. MaxP: Chunk → Document

Content retrieval produces chunks, but final ranking operates on documents.

For each content channel:

1. retrieve chunks
2. group chunks by `document_id`
3. identify the best chunk for each document
4. use that best chunk's rank/score as the document's channel evidence
5. preserve the best passage as evidence

Conceptually:

```text
document_score(d) = max(chunk_score)
```

The important property is:

> Multiple chunks from the same document do not give that document multiple votes in RRF.

This prevents long documents from winning simply because they contain many individually matching chunks.

MaxP happens **before RRF**.

---

# 16. RRF Fusion

RRF fuses the four topical document lists:

- title BM25
- content BM25 after MaxP
- title vector
- content vector after MaxP

Initial configuration:

```text
k = 60
equal channel weights
```

RRF is a rank-fusion mechanism, not the complete search algorithm.

Identity is outside RRF.

Metadata is outside RRF.

Raw BM25/vector scores must not simply be added together because their scales are not directly comparable.

A healthy channel that returns zero results still counts as an active channel.

A failed channel is excluded from the denominator.

---

# 17. Metadata Score Adjustment

Metadata contributes a small bounded adjustment after topical fusion.

Initial configuration from the research plan:

```text
HIGH confidence weight   = 1.0
MEDIUM confidence weight = 0.6
LOW confidence weight    = 0.3

positive adjustment max ≈ +0.08
contradiction penalty max ≈ -0.03
```

These are **initial evaluation parameters**, not architecture truths.

They must be configurable and evaluated.

Metadata should not become a hidden fifth RRF channel.

---

# 18. Identity + Final Ranking

The conceptual final order is:

1. mandatory eligibility
2. query-aware identity tier
3. topical RRF + bounded metadata adjustment
4. deterministic tie breakers

Initial tie breakers:

```text
base topical score
best topical channel rank
metadata candidate rank
document_id
```

The exact identity-tier policy must depend on the type of identity evidence supplied by the query.

---

# 19. Metadata-Dominant Queries

Some queries may contain little or no topical text.

Examples:

```text
PDFs
files modified yesterday
large files
presentations
```

For these queries, topical RRF may be absent or weak.

The search system must still be able to return useful metadata-driven results using:

- metadata predicates
- deterministic implied sort where recognized
- SQLite authoritative metadata

No fabricated semantic query should be created merely to force topical retrieval.

---

# 20. Result Evidence

Every useful result should expose deterministic evidence.

Conceptual evidence types:

- identity
- title lexical
- content lexical
- title semantic
- content semantic
- metadata
- degradation

Evidence should answer:

> Why did this file appear?

Examples:

```text
Filename matches "IAI_Endsem".
```

```text
Contains the exact phrase "Kalman filter".
```

```text
Best matching passage discusses pedestrian detection under rain.
```

```text
Matches the remembered PDF type and modification period.
```

```text
Included despite the Word-document hint because stronger content evidence supported it.
```

Do not expose raw fusion scores as the primary user explanation.

---

# 21. SQLite vs LanceDB

SQLite remains authoritative for:

- document identity
- path
- filename
- extension
- size
- created time
- modified time
- processing state
- content hash

LanceDB is the derived retrieval representation.

LanceDB may contain projections needed for efficient retrieval/filtering, but these are not authoritative.

The final result should hydrate authoritative document metadata from SQLite.

---

# 22. LanceDB Metadata Projections

Both `documents` and `chunks` need the metadata required for prefiltered retrieval.

Initial projections:

- document type / extension
- modified time
- created time
- size
- source path

Identity keys remain authoritative in SQLite.

Metadata-only updates must update LanceDB projections without re-embedding.

---

# 23. Failure and Degradation

V1 must fail gracefully by channel.

Examples:

- embedding failure → skip semantic channels
- title FTS failure → content/semantic channels continue
- content FTS failure → other channels continue
- vector failure → lexical channels continue
- strict filter failure → relaxed retrieval continues
- unresolved date → do not invent a date range
- SQLite unavailable → search cannot safely provide authoritative identity/metadata
- LanceDB unavailable → SQLite-only identity/metadata retrieval may still provide partial results
- vague query → browse/recent behavior only when a deterministic clue/mode exists
- no candidates → truthful no-results response

The system must never fabricate retrieval evidence.

---

# 24. Explicit V1 Non-Goals

Do not add these to V1:

- LLM query gatekeeper
- LLM query expansion
- generative query rewriting
- cross-encoder reranker
- learned ranking model
- neural metadata classifier
- automatic synonym expansion
- raw score addition across BM25/vector
- hard intersection of lexical and semantic retrieval
- global recency boost
- MMR diversification

These can be evaluated later using judged queries.

---

# 25. Evaluation Principles

The retrieval architecture must be evaluated using a fixed query set.

Target:

- at least 60 representative queries

Include:

- exact identity
- identifier/number
- exact phrase
- semantic concept
- correct metadata
- incorrect metadata
- hedged metadata
- metadata-dominant queries
- unresolved metadata
- channel failures

Metrics:

- Identity Success@1
- MRR@10
- Recall@10
- Recall@20
- nDCG@10
- metadata escape Recall@20
- evidence accuracy
- zero-result rate
- cold/warm p50 and p95 latency
- memory usage

Ablations:

1. lexical only
2. semantic only
3. four-channel RRF without metadata
4. strict metadata only without relaxed retrieval
5. dual-lane metadata design

Parameters should be tuned only against the fixed evaluation set.

---

# 26. Architectural Summary

The V1 search pipeline is:

```text
Memory fragment
   ↓
Deterministic query planner
   ↓
Identity + metadata + topical evidence
   ↓
SQLite identity/metadata
+
LanceDB:
    title BM25
    content BM25
    title vector
    content vector
   ↓
Content MaxP
   ↓
Four-channel RRF
   ↓
Bounded metadata adjustment
   ↓
Query-aware identity priority
   ↓
SQLite hydration
   ↓
Deterministic evidence
   ↓
SearchResult
```

The key design principle is:

> **Use every reliable clue the user provides, but never let an uncertain memory fragment become a hard constraint unless the query explicitly makes it one.**
