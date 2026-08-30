# OpenX Scenario Workbench

English | [中文](README.md)

A small, reproducible workbench for inspecting ASAM OpenSCENARIO XML (`.xosc`) and OpenDRIVE (`.xodr`) files. It turns scenario entities, actions, triggers, positions, and road-network metadata into a shared structured representation and provides a 中文 / English interface.

## Current capabilities

- Import an `.xosc` file together with an `.xodr` file
- Extract scenario headers, road references, entities, actions, triggers, and positions
- Summarize roads, lanes, junctions, signals, and static objects
- Check whether the referenced road file matches the uploaded file
- Inspect the summary and download it as JSON in the web UI
- Parse files from the command line for future retrieval or agent workflows

This is intentionally a focused MVP. It is not a complete ASAM conformance validator and contains no private formats, company assets, or internal data.

## Quick start

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
streamlit run src/openx_workbench/app.py
```

Command-line usage:

```bash
openx-inspect scenario.xosc road.xodr --language en
```

## Fetch a public example

Third-party scenarios are not copied directly into this repository. The following command downloads public files from the official esmini repository and keeps its license alongside them:

```bash
python scripts/fetch_esmini_demo.py
```

Downloaded files are stored under `examples/esmini/` and are ignored by Git. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Project direction

The current release focuses on explainable OpenX inspection. Its shared data layer can later support semantic search, natural-language filtering, deterministic quality checks, and agent tools without coupling model logic to the parser or UI.

## License

Project code is released under the MIT License. Downloaded third-party examples remain under their respective licenses.
