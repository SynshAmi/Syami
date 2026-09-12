# Syami Retrieval Implementation Plan

## 1. Purpose

This document is the implementation contract for building Syami V1 retrieval/search.

It is written so that implementation can be delegated to Antigravity in small, controlled steps.

The implementation must follow this document and `QUERY_ARCHITECTURE.md`.

Do not introduce unrelated refactors.

Do not create speculative abstractions.

Do not add LLM-based retrieval, reranking, query expansion, or learned ranking in V1.

---

# 2. Current Repository Baseline

Relevant current structure:

```text
src/syami/
├── domain/
│   └── document.py
├── application/
│   ├── indexing.py
│   └── documents/
│       ├── chunker.py
│       ├── processing.py
│       ├── processor.py
│       ├── scheduler.py
│       └── worker.py
└── infrastructure/
    ├── database/
    │   └── db.py
    ├── documents/
    │   ├── docx_processor.py
    │   ├── pdf_processor.py
    │   ├── pptx_processor.py
    │   └── text_processor.py
    ├── embedding/
    │   └── embedder.py
    ├── filesystem/
    │   ├── hasher.py
    │   └── scanner.py
    └── vector/
        └── lancedb_store.py
```

Search does not currently exist.

Current relevant dependencies:

```text
LanceDB 0.37.1
sentence-transformers 5.7.0
all-MiniLM-L6-v2
384-dimensional normalized embeddings
```

Current LanceDB tables:

### documents

```text
document_id
title
title_vector
source_path
document_type
```

FTS index:

```text
title
```

### chunks

```text
document_id
chunk_index
text
vector
title
source_path
document_type
unit_type
```

FTS index:

```text
text
```

No vector indexes currently exist.

Flat vector search is acceptable for the current local MVP scale.

---

# 3. Non-Negotiable Architecture Boundaries

Use the existing layered architecture:

```text
interface / command boundary
        ↓
application orchestration
        ↓
domain/core logic
        ↓
infrastructure
```

Search responsibilities:

```text
domain/search.py
    pure search value objects / contracts

application/search/planning.py
    deterministic query interpretation

application/search/ranking.py
    pure ranking algorithms

application/search/execution.py
    search orchestration

infrastructure/database/db.py
    SQLite identity/metadata queries

infrastructure/vector/lancedb_store.py
    FTS/vector retrieval and LanceDB filtering

infrastructure/embedding/embedder.py
    query embedding boundary
```

Do not put search orchestration inside `processing.py`.

Do not put RRF inside LanceDB infrastructure.

Do not make domain objects depend on SQLite/LanceDB.

---

# 4. Implementation Rules for Antigravity

For every implementation step:

1. Inspect the current file before editing.
2. Implement only the requested step.
3. Do not modify unrelated files.
4. Do not silently redesign an approved contract.
5. Preserve existing public behavior unless the step explicitly changes it.
6. Prefer small deterministic functions.
7. Keep pure ranking functions free of I/O.
8. Use parameterized SQLite queries.
9. Use LanceDB's actual installed APIs rather than guessed APIs.
10. Do not swallow exceptions with broad `except Exception: pass` in newly implemented retrieval code.
11. Preserve channel-level failure isolation.
12. Add targeted tests for behavior introduced by the step.
13. Run only the relevant checks/tests after the step.
14. Report changed files and checks performed.
15. Stop after the requested step and wait for the next instruction.

The implementation should not turn into a broad test/refactor loop.

---

# 5. Phase 0 — Freeze Contracts and Baseline

## Goal

Create the stable contracts before implementing retrieval behavior.

## Tasks

### 0.1 Create `domain/search.py`

Define pure value objects needed by the retrieval system.

At minimum, model the concepts:

- `SearchQueryPlan`
- `IdentityProbe`
- `MetadataPredicate`
- identity kind
- metadata confidence
- metadata enforcement
- metadata precision
- retrieval candidate
- evidence
- search result

Use dataclasses/enums where appropriate.

Do not put database calls or LanceDB code here.

Do not implement retrieval algorithms here.

### 0.2 Establish result/evidence contracts

The result contract must be capable of representing:

- authoritative document metadata
- identity tier
- topical score
- metadata adjustment
- final score
- evidence
- passages
- diagnostics/degradation

### 0.3 Add initial test fixtures

Create the test structure:

```text
tests/
├── unit/
└── integration/
```

Do not build the full evaluation corpus yet.

## Acceptance Criteria

- Domain contracts import successfully.
- No infrastructure dependency exists in `domain/search.py`.
- Existing application code still imports/runs.
- No search behavior is implemented yet.

---

# 6. Phase 1 — SQLite Identity and Metadata Foundation

## Goal

Make SQLite capable of authoritative identity lookup and metadata candidate retrieval.

### 1.1 Add identity keys

Add to `documents`:

```text
filename_key TEXT
stem_key TEXT
path_key TEXT
```

Keys must be generated deterministically.

Normalization:

- NFKC
- casefold
- whitespace normalization
- path separator normalization
- appropriate stem normalization

### 1.2 Backward-compatible local schema evolution

`CREATE TABLE IF NOT EXISTS` does not alter an existing table.

Therefore `init_db()` must detect missing columns using `PRAGMA table_info(documents)` and add them safely.

Do not introduce a migration framework at this stage.

Add indexes:

```text
idx_documents_filename_key
idx_documents_stem_key
idx_documents_path_key
```

### 1.3 Update indexing

When a document is inserted or its metadata changes:

- update identity keys
- preserve content hash behavior
- do not force reprocessing merely because path/filename metadata changed

Identity key generation should be centralized rather than duplicated across multiple functions.

### 1.4 Add identity lookup functions

Infrastructure should expose parameterized operations for:

- exact filename identity
- exact stem identity
- exact path identity
- bounded identifier lookup where applicable
- metadata candidate retrieval
- authoritative document hydration

Keep arbitrary substring scanning out of identity lookup.

### 1.5 Metadata-only synchronization

When a file is renamed/moved without content change:

- SQLite remains authoritative
- LanceDB metadata projections must eventually be updated
- no re-embedding is required

This synchronization is completed in Phase 3 when LanceDB infrastructure is changed.

### 1.6 Deletion synchronization contract

When scan reconciliation removes a document from SQLite:

- corresponding LanceDB records must also be deleted

Do not implement the LanceDB deletion call until Phase 3, but explicitly preserve the hook/contract needed to do so.

## Acceptance Criteria

- Existing DB can initialize with new columns.
- Existing local DBs do not require manual recreation.
- New/updated documents receive correct identity keys.
- Exact identity lookup is parameterized and bounded.
- Metadata hydration returns authoritative SQLite fields.
- No retrieval logic is added to SQLite.

---

# 7. Phase 2 — Deterministic Query Planning

## Goal

Convert a memory-oriented user query into a bounded `SearchQueryPlan`.

Create:

```text
src/syami/application/search/
    __init__.py
    planning.py
```

## 2.1 Normalization

Implement deterministic normalization.

- NFKC unicode normalization.
- Smart / curly quote normalization (`“ ” ‘ ’ « »` mapped to standard ASCII quotes).
- Whitespace stripping.

Do not modify the user's original text (`original_text` remains untouched).

Preserve enough source information for evidence spans.

## 2.2 Identity recognition

Recognize:

- paths
- filenames with extensions
- distinctive stems
- identifier sequences

Identity classification must be query-aware.

Do not globally rank identity types using a fixed:

```text
path > filename > stem
```

rule.

For pure identity-dominant queries (e.g. `Transformers Notes.pdf` or `C:/docs/report.pdf`):
- `identity_probes` are populated.
- `topical_text = None` and `semantic_text = None` (preventing filenames/paths from polluting vector search).

## 2.3 Metadata recognition

Support V1 deterministic forms for:

- extension/type
- modified time (including relative dates such as `today`, `yesterday`, `this week`, `last week`, `this month`, `last year`)
- created time
- file time
- size
- path cues (folder containment)

Support explicit restrictive wording such as:

```text
only PDFs
```

Support precise unhedged remembered metadata as strict-preferred.

Support hedged wording as soft-only.

Do not guess unresolved relative periods.

Example:

```text
last semester
```

must remain unresolved unless a deterministic configured interpretation exists.

## 2.4 Query confidence

Represent confidence of the user's stated clue separately from retrieval evidence strength.

Do not use confidence as a probability.

## 2.5 Topical and semantic text

Produce clean, topic-focused:

```text
topical_text
semantic_text
```

- Strip command prefixes (`find me`, `search for`, etc.).
- Strip conversational scaffolding patterns (e.g. `in which content was about`, `had some questions about`, `discusses`, `talks about`).
- Strip conversational connectors, prepositions, and generic entity words (`about`, `on`, `regarding`, `the`, `file`, `document`, etc.).
- Isolate the broad topic without conversational filler or command scaffolding.
- Exclude quoted spans from the broad topical candidate.
- Fall back to remembered clues for topical/semantic retrieval input when the query is clue-only (no distinct broad topic keywords).
- If topical text exists, all four topical channels remain eligible.

## 2.6 Quoted phrases and multiple remembered clues

Extract quoted phrases safely:

- Support zero, one, or multiple remembered content clues.
- Case-insensitive deduplication (preserving the casing of the first occurrence).
- Remove quoted spans from working text during broad topic extraction.
- Quoted phrases are used for lexical retrieval and exact-match verification.
- Do not make content phrases identity evidence.

## 2.7 Canonical Example: Broad Topic + Multiple Clues + Metadata

Example query:

> *"Find the PDF in which content was about Java top 50 interview questions. It had some questions about ‘what is IOC in Spring’, ‘what is dependency injection’, and ‘what is the difference between JDK, JRE and JVM’."*

The planner produces:

* **Metadata**: `extension = .pdf` (confidence: MEDIUM, enforcement: STRICT_PREFERRED)
* **Broad topical text**: `Java top 50 interview questions`
* **Semantic text**: `Java top 50 interview questions`
* **Specific lexical clues**:
  * `what is IOC in Spring`
  * `what is dependency injection`
  * `what is the difference between JDK, JRE and JVM`
* **Identity probes**: `[]` (none)
* **Mode**: `SearchMode.STANDARD`

## 2.8 Mode / implied sort

Support deterministic modes where justified.

Examples:

- `IDENTITY_DOMINANT`: query is purely a path or filename without separate topical content
- `METADATA_DOMINANT`: metadata predicates exist with no topical text or quoted phrases
- `RECENT`: explicit recent-file browsing (`recent files`, `latest documents`)
- `STANDARD`: standard multi-channel search

Do not invent a mode from vague wording.

## 2.9 Diagnostics

Record parser ambiguities or unresolved metadata (e.g. `last semester`, empty queries).

## Acceptance Criteria

Unit tests cover:

- filename extraction
- stem extraction
- path recognition
- single and multiple quoted phrases / remembered questions
- case-insensitive clue deduplication
- smart / curly quote normalization
- broad topic + single clue
- broad topic + multiple clues
- PDF metadata + topic + multiple clues
- pure topical query (no clues)
- clue-only query (fallback to clues for semantic text)
- date/file-type metadata mixed with topical text
- identity-only query (`semantic_text = None`)
- canonical Java top 50 interview questions example
- explicit type predicates
- strict-preferred metadata
- soft-only metadata
- unresolved date language
- topical text extraction and conversational scaffolding stripping
- metadata-dominant query planning

The planner is deterministic and contains no external I/O.

---

# 8. Phase 3 — LanceDB Retrieval Infrastructure

## Goal

Extend the existing LanceDB infrastructure without moving ranking logic into it.

Modify:

```text
src/syami/infrastructure/vector/lancedb_store.py
```

## 3.1 Add FTS retrieval with filters

Expose typed operations for:

- title lexical search
- content lexical search
- support for zero, one, or multiple lexical clue queries (searching each clue in content FTS) and merging results at document level

Support optional LanceDB `where` filters.

Use prefiltering where appropriate.

Do not build raw filter strings from untrusted user input without safe construction/validation.

## 3.2 Add vector retrieval

Expose:

- title vector search
- chunk vector search

Important:

```text
documents.title_vector
chunks.vector
```

The title vector search must explicitly use:

```text
vector_column_name="title_vector"
```

Do not assume the vector column is called `vector` in both tables.

## 3.3 Query vector contract

Add the required vector-search boundary while preserving:

```text
all-MiniLM-L6-v2
384 dimensions
normalized vectors
```

Do not change the embedding model as part of this phase.

## 3.4 Filter projections

Ensure LanceDB records contain:

- document type / extension
- modified time
- created time
- size
- source path

Both documents and chunks need fields required for prefiltered searches.

## 3.5 Metadata-only updates

Expose infrastructure operations that can update metadata projections without regenerating embeddings.

At minimum support updates for:

- source path
- title
- relevant metadata projections

## 3.6 Deletion synchronization

Expose:

```text
delete_document(document_id)
```

for both LanceDB tables.

Hook scan reconciliation so deleted SQLite documents also remove their derived LanceDB records.

## 3.7 Index creation

Do not add vector indexes merely because vector search exists.

Current scale permits exact flat search.

FTS indexes remain required.

Scalar indexes may be added when measurement demonstrates they are useful.

## Acceptance Criteria

Integration tests verify:

- title FTS
- content FTS
- title vector search
- content vector search
- filtered FTS
- filtered vector search
- metadata-only update
- document deletion
- correct title vector column selection

No RRF or search orchestration belongs here.

---

# 9. Phase 4 — Pure Ranking Algorithms

## Goal

Implement deterministic ranking with no I/O.

Create:

```text
src/syami/application/search/ranking.py
```

## 4.1 RetrievalCandidate

Candidates should carry enough information for:

- document ID
- channel
- rank
- raw retrieval score
- chunk evidence where applicable
- metadata match evidence

Raw scores are diagnostics/evidence, not directly summed across channels.

## 4.2 MaxP

For content channels:

```text
chunks
  ↓
group by document_id
  ↓
best chunk per document
  ↓
document-level ranked list
```

Preserve:

- best chunk index
- best passage/snippet
- raw score
- rank

Multiple chunks from the same document must not generate multiple RRF votes.

Multiple distinct remembered clues (e.g. 3 distinct questions in a query) may contribute bounded accumulated evidence, but repeated matches of the exact same clue across multiple chunks in a single document must not be treated as multiple independent clues.

## 4.3 RRF

Implement:

```text
k = 60
equal channel weights
```

Fuse:

- title BM25
- content BM25 after MaxP
- title vector
- content vector after MaxP

Healthy empty channels remain active.

Failed channels are excluded from the active-channel denominator.

## 4.4 Metadata adjustment

Implement the bounded metadata adjustment.

Initial parameters:

```text
HIGH = 1.0
MEDIUM = 0.6
LOW = 0.3

positive cap ≈ +0.08
negative cap ≈ -0.03
```

These must be configuration/constants that can later be evaluated.

Do not describe them as theoretically optimal.

## 4.5 Deterministic tie-breaking

Implement:

1. query-aware identity tier
2. final score
3. base topical score
4. best topical rank
5. metadata candidate rank
6. document ID

The exact identity policy must be driven by the identity evidence present in the query.

## Acceptance Criteria

Unit tests cover:

- MaxP
- duplicate chunk suppression
- RRF with k=60
- healthy empty channels
- failed channel exclusion
- metadata positive/negative adjustment
- deterministic ties
- identity tier ordering

Ranking code must be pure.

---

# 10. Phase 5 — Search Execution / Orchestration

## Goal

Create the application-level search coordinator.

Create:

```text
src/syami/application/search/execution.py
```

## 10.1 SearchCoordinator responsibilities

It should:

1. receive raw user query
2. call query planner
3. execute mandatory eligibility
4. execute identity lookup
5. execute topical retrieval channels
6. execute metadata lanes
7. aggregate chunk results with MaxP
8. fuse topical channels with RRF
9. apply metadata adjustment
10. apply query-aware identity priority
11. hydrate authoritative documents from SQLite
12. assemble evidence
13. return `SearchResult`

It should not contain low-level SQL or LanceDB API details.

## 10.2 Candidate budgets

Initial configuration:

```text
Identity: 25
Metadata: 100
Title BM25: 50
Content BM25: 200 → 400 if document diversity is insufficient
Title vector: 50
Content vector: 200 → 400 if document diversity is insufficient
```

These are starting values.

Do not hard-code them throughout the codebase.

## 10.3 Metadata lanes

Always run the relaxed lane.

When strict-preferred predicates exist:

```text
relaxed = U
strict  = U ∧ H
```

Do not make relaxed retrieval merely a zero-result fallback.

Do not create an additional RRF vote for the strict lane.

## 10.4 Identity

Identity is evaluated separately.

Do not let identity candidates receive a second topical vote simply because they were retrieved through identity.

Identity priority is applied during final ordering.

## 10.5 Hydration

After ranking:

- take top result IDs
- retrieve authoritative document metadata from SQLite
- preserve ranking order
- assemble the final result objects

SQLite is the source of truth.

## Acceptance Criteria

Integration test demonstrates:

```text
query
 → planner
 → SQLite identity/metadata
 → LanceDB retrieval
 → MaxP
 → RRF
 → metadata adjustment
 → hydration
 → SearchResult
```

The result order is deterministic.

---

# 11. Phase 6 — Evidence and Degradation

## Goal

Make retrieval understandable and robust.

## 11.1 Evidence assembly

Generate deterministic evidence for:

- identity
- title lexical
- content lexical (including which specific remembered clues matched)
- title semantic
- content semantic
- metadata

Results should eventually be able to explicitly show which remembered clues matched, where supported by the evidence model.

Keep evidence tied to actual retrieved data.

## 11.2 Passage selection

Retain at most two useful passages per final document.

Prefer:

- strongest lexical passage
- strongest semantic passage

The second passage should ideally be non-adjacent and add distinct evidence.

Do not implement MMR in V1.

## 11.3 Failure isolation

Implement channel-level degradation:

```text
embedding failure
    → semantic channels skipped

FTS failure
    → remaining channels continue

vector failure
    → lexical channels continue

strict filter failure
    → relaxed lane continues

LanceDB unavailable
    → SQLite-only partial retrieval where safe

SQLite unavailable
    → authoritative search cannot proceed safely
```

Diagnostics must explain degradation without pretending the failed channel produced results.

## Acceptance Criteria

Tests verify each major failure mode produces safe partial behavior where possible.

---

# 12. Phase 7 — Interface Integration

## Goal

Expose the search application service through the existing interface/command boundary.

The interface layer should:

- receive user input
- call `SearchCoordinator`
- format results

It should not:

- parse metadata
- calculate RRF
- query LanceDB directly
- query SQLite directly

If no search command/interface currently exists, add the smallest appropriate boundary rather than creating a parallel CLI architecture.

---

# 13. Phase 8 — Evaluation Harness

## Goal

Evaluate the actual retrieval system before tuning parameters.

Create a fixed evaluation dataset of at least 60 queries.

Categories:

### Identity

- exact filename
- exact path
- exact stem
- identifier sequence

### Lexical

- exact content phrase
- distinctive title words

### Multiple / Remembered Clues

- broad topic + multiple remembered questions
- partial clue matches (some remembered clues match in document, some do not)
- duplicate remembered clues in query
- clue-only queries (no broad topic, only remembered questions)
- topic + file type + multiple remembered clues (e.g. Java top 50 interview questions PDF)

### Semantic

- conceptual descriptions

### Metadata

- correct file type
- correct date
- correct size
- path cues

### Incorrect memory

- wrong file type
- wrong date
- wrong size

### Hedged memory

- `I think it was a Word file`
- similar uncertainty

### Metadata-dominant

- recent PDFs
- large presentations
- files in a directory

### Failure

- unresolved date
- embedding unavailable
- FTS failure
- vector failure

---

# 14. Evaluation Metrics

Measure:

- Identity Success@1
- MRR@10
- Recall@10
- Recall@20
- nDCG@10
- metadata escape Recall@20
- evidence accuracy
- zero-result rate
- cold p50/p95
- warm p50/p95
- memory usage

The evaluation set must remain fixed while comparing implementations/configurations.

---

# 15. Required Ablations

Compare:

1. lexical only
2. semantic only
3. four-channel RRF without metadata
4. strict metadata only without relaxed retrieval
5. dual-lane metadata architecture

Use these to determine whether the additional complexity is justified.

---

# 16. Parameters That Are NOT Locked Forever

The following are initial values only:

```text
RRF k = 60
metadata confidence weights
metadata +0.08 cap
metadata -0.03 cap
candidate budgets
content expansion threshold
recent-date half-life
```

Do not tune these casually during implementation.

First implement them cleanly and evaluate.

---

# 17. Data Consistency Requirements

These are part of retrieval correctness, not optional cleanup.

### Rename/move without content change

Must result in:

```text
SQLite updated
LanceDB projections updated
embeddings preserved
```

No unnecessary re-embedding.

### File deletion

Must result in:

```text
SQLite document removed
LanceDB document row removed
LanceDB chunk rows removed
```

No stale searchable records.

### Reprocessing

When content changes:

```text
SQLite content hash/status updated
old LanceDB representation replaced
new chunks/vectors written
```

The existing replacement semantics should be preserved.

---

# 18. Testing Strategy

There are currently no existing tests.

Use:

```text
tests/unit/
tests/integration/
```

Suggested tests:

```text
tests/unit/test_query_planner.py
tests/unit/test_ranking.py

tests/integration/test_lancedb_search.py
tests/integration/test_search_coordinator.py
tests/integration/test_index_consistency.py
```

Tests should be targeted.

Do not create a huge test framework before retrieval behavior exists.

---

# 19. Recommended Implementation Order

Execute in exactly this dependency order:

```text
Phase 0
Contracts
  ↓
Phase 1
SQLite identity + metadata
  ↓
Phase 2
Query planning
  ↓
Phase 3
LanceDB retrieval infrastructure
  ↓
Phase 4
Pure ranking
  ↓
Phase 5
Search orchestration
  ↓
Phase 6
Evidence + degradation
  ↓
Phase 7
Interface integration
  ↓
Phase 8
Evaluation
```

Do not skip directly to `SearchCoordinator`.

Do not implement ranking inside infrastructure first.

---

# 20. Definition of Done for V1

V1 is complete when:

- deterministic query planning works
- identity lookup works
- title/content BM25 works
- title/content vector retrieval works
- metadata filters work
- strict + relaxed metadata retrieval works
- MaxP prevents duplicate document votes
- RRF fuses four topical channels
- identity is handled outside RRF
- metadata is handled outside RRF
- final results hydrate authoritative SQLite metadata
- evidence explains why results matched
- channel failures degrade safely
- rename/move synchronization works
- deletion synchronization works
- tests cover core retrieval behavior
- evaluation has been run on the fixed query set
- parameters are documented with measured results

---

# 21. Antigravity Execution Protocol

When given an implementation instruction such as:

> Implement Phase 1.

Antigravity must:

1. Read this document.
2. Read the current relevant files.
3. Implement only Phase 1.
4. Show exactly which files changed.
5. Run targeted checks/tests for Phase 1.
6. Report any discovered incompatibility.
7. Do not proceed into Phase 2.
8. Do not create unrelated files/refactors.

For a sub-step instruction such as:

> Implement Phase 3.2 vector retrieval.

Only implement that sub-step and its necessary tests.

If the current code conflicts with this plan, **stop and report the conflict before inventing a new architecture**.

---

# 22. Final Architectural Rule

The implementation must preserve this separation:

```text
User memory
    ↓
Query planning
    ↓
Evidence retrieval
    ↓
Document-level ranking
    ↓
Authoritative hydration
    ↓
Evidence explanation
```

The system should use the user's reliable clues aggressively, but should never turn uncertain memory into an unjustified hard constraint.
