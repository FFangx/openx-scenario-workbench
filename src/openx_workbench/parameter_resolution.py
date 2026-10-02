"""Bounded lexical parameter resolution for the parsed view, never source XML."""
from __future__ import annotations

import ast
import math
import operator
import re
from xml.etree import ElementTree as ET


def resolve_parameters(root: ET.Element) -> tuple[dict, list[dict], list[dict], list[dict]]:
    paths, declarations, issues, resolutions = {}, [], [], []
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod}

    def resolve(value, scope, trail=()):
        if value.startswith("${") and value.endswith("}"):
            expression = value[2:-1]
            if len(expression) > 256:
                raise ValueError("expression exceeds 256 characters")
            names = {}

            def variable(match):
                key = f"p{len(names)}"
                names[key] = float(resolve("$" + match[1], scope, trail))
                return key

            tree = ast.parse(re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", variable, expression), mode="eval")
            if len(list(ast.walk(tree))) > 64:
                raise ValueError("expression exceeds 64 nodes")

            def evaluate(node):
                if isinstance(node, ast.Constant) and type(node.value) in {float, int}:
                    result = node.value
                elif isinstance(node, ast.Name) and node.id in names:
                    result = names[node.id]
                elif isinstance(node, ast.BinOp) and type(node.op) in binary:
                    result = binary[type(node.op)](evaluate(node.left), evaluate(node.right))
                elif isinstance(node, ast.UnaryOp) and type(node.op) in {ast.UAdd, ast.USub}:
                    result = evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
                else:
                    raise ValueError("unsupported parameter expression")
                if not math.isfinite(result):
                    raise ValueError("non-finite parameter expression")
                return result

            return str(evaluate(tree.body))
        if value.startswith("$"):
            name = value[1:]
            if name not in scope:
                raise ValueError(f"undeclared parameter: {name}")
            declaration, owner_scope = scope[name]
            identity = id(declaration)
            if identity in trail or len(trail) >= 32:
                raise ValueError(f"cyclic or excessive parameter chain: {name}")
            resolved = resolve(declaration.get("value", ""), owner_scope, (*trail, identity))
            kind = declaration.get("parameterType")
            if kind in {"double", "integer", "unsignedInt", "unsignedShort"}:
                number = float(resolved)
                if not math.isfinite(number) or (kind != "double" and not number.is_integer()):
                    raise ValueError(f"invalid {kind} parameter: {name}")
                if kind.startswith("unsigned") and number < 0:
                    raise ValueError(f"negative unsigned parameter: {name}")
            return resolved
        return value

    def visit(node, inherited, path):
        paths[node] = path
        scope = dict(inherited)
        local = [decl for container in node if container.tag.rsplit("}", 1)[-1] == "ParameterDeclarations"
                 for decl in container if decl.tag.rsplit("}", 1)[-1] == "ParameterDeclaration"]
        local_names = set()
        ambiguous_names = set()
        for declaration in local:
            name = declaration.get("name", "")
            # 51sim also prefixes declaration names with the reference marker.
            # Accept that spelling only in the parsed view; retain the original
            # declaration in the audit and never pick a conflicting binding.
            canonical = name[1:] if re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", name) else name
            if canonical in local_names:
                ambiguous_names.add(canonical)
            local_names.add(canonical)
            scope[canonical] = (declaration, scope)
            declarations.append({"scope": path, **declaration.attrib})
        for name in sorted(ambiguous_names):
            scope.pop(name, None)
            issues.append({"path": path, "attribute": "name", "raw": name,
                           "detail": f"ambiguous parameter declarations: {name}"})
        # Keep declaration expressions intact: aliases resolve in their defining scope.
        if node.tag.rsplit("}", 1)[-1] != "ParameterDeclaration":
            for key, raw in list(node.attrib.items()):
                if not raw.startswith("$"):
                    continue
                try:
                    resolved = resolve(raw, scope)
                    node.set(key, resolved)
                    resolutions.append({"path": path, "attribute": key, "raw": raw, "resolved": resolved})
                except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
                    issues.append({"path": path, "attribute": key, "raw": raw, "detail": str(exc)})
        counts = {}
        for child in node:
            tag = child.tag.rsplit("}", 1)[-1]
            counts[tag] = counts.get(tag, 0) + 1
            visit(child, scope, f"{path}/{tag}[{counts[tag]}]")

    visit(root, {}, "/OpenSCENARIO[1]")
    return paths, declarations, issues, resolutions
