# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: an autonomous-driving engineering candidate demonstrating applied scenario-engineering capability during portfolio review, interviews, and thesis discussion.

Secondary: reviewers who need to understand the provenance, structure, and reuse rationale of an ADAS scenario without learning the implementation first.

These user definitions are inferred from the explicit project and résumé context and remain open for later confirmation.

## Product Purpose

OpenX Scenario Workbench turns an ADAS requirement in a PDF into a traceable decision about whether an existing paired OpenSCENARIO/OpenDRIVE asset can be reused, must be modified, or should be rebuilt. Success means a reviewer can follow the complete evidence chain in one short demonstration.

## Positioning

The product joins document evidence, scenario structure, road geometry, and retrieval scores in one deterministic workflow. Vector similarity recalls candidates; explicit OpenX facts decide compatibility and explain the result.

## Operating Context

The core demonstration starts with a text-based ADAS PDF and a small library of paired `.xosc` and `.xodr` files. The user selects an extracted requirement, builds or uploads the asset library, reviews ranked candidates, and inspects the evidence and change set behind the reuse recommendation.

## Capabilities and Constraints

- Bilingual English/Chinese web interface and command-line tools.
- Page-aware PDF scene extraction with section IDs and source evidence.
- Paired OpenSCENARIO/OpenDRIVE parsing and catalog construction.
- Offline hashing retrieval and optional local BGE semantic embeddings.
- Scenario, participant-interaction, and road-geometry reranking.
- Grounded reuse classification and estimated change cost.
- No full simulation, ASAM conformance certification, OCR, or complete OpenX coverage.
- ScenarioManager-compatible `.sim` extraction is implemented for the observed ZIP layout, including map-ID-to-embedded-XODR resolution.
- The public repository must contain no private internship documents, assets, customer configuration, or evaluation data.

## Evidence on Hand

- Public esmini example under `examples/esmini/` with its upstream license.
- Synthetic minimal OpenX fixtures under `tests/fixtures/`.
- Architecture and limitations documented in `README.md`, `docs/ARCHITECTURE.md`, and `DEVELOPMENT_PLAN.md`.
- No licensed public ADAS PDF corpus or multi-candidate public demo library is currently bundled.

## Product Principles

1. Evidence before recommendation: every decision exposes its source text and parsed facts.
2. Structure outranks similarity: semantic recall cannot override a blocking incompatibility.
3. One visible workflow: document, library, retrieval, and decision read as consecutive stages.
4. Public and reproducible: the demonstration runs locally without private data or mandatory cloud services.
5. Engineering honesty: unsupported behaviors and unknown topology remain explicit.

## Accessibility & Inclusion

The interface should support keyboard focus, readable contrast, responsive layouts, and complete English/Chinese labels. Dense engineering information may remain tabular when a table is the clearest representation.
