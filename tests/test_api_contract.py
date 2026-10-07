"""The OpenAPI document describes every JSON route; conftest.api_contract checks responses against it."""
from typing import get_type_hints

import pytest

pytest.importorskip("fastapi")

from fastapi.responses import Response
from fastapi.routing import APIRoute

from openx_workbench.api import app


def test_every_json_route_documents_its_response():
    undocumented = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        returns = get_type_hints(route.endpoint).get("return")
        if isinstance(returns, type) and issubclass(returns, Response):
            continue  # files, images and downloads
        if 200 not in route.responses:
            undocumented.append(f"{sorted(route.methods)} {route.path}")
    assert not undocumented


def test_request_and_response_schemas_are_not_split():
    # A model used both ways with different shapes would get "-Input"/"-Output" variants in the web types.
    schemas = app.openapi()["components"]["schemas"]
    assert not [name for name in schemas if name.endswith(("-Input", "-Output"))]
