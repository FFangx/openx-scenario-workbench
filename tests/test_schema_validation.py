import hashlib
import json

import pytest

from openx_workbench.schema_validation import validate_xml


def registry(tmp_path):
    pytest.importorskip("lxml")
    pytest.importorskip("xmlschema")
    # Authored schema tests version routing/diagnostics. This is not an ASAM XSD.
    schema = b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="OpenSCENARIO"><xs:complexType><xs:sequence>
        <xs:element name="FileHeader"><xs:complexType>
          <xs:attribute name="revMajor" type="xs:integer" use="required"/>
          <xs:attribute name="revMinor" type="xs:integer" use="required"/>
        </xs:complexType></xs:element>
        <xs:element name="RequiredBody"/>
      </xs:sequence></xs:complexType></xs:element>
    </xs:schema>'''
    (tmp_path / "authored.xsd").write_bytes(schema)
    (tmp_path / "registry.json").write_text(json.dumps({
        "revision": "authored", "entries": {"OpenSCENARIO:1.2": "authored.xsd"},
        "sha256": {"authored.xsd": hashlib.sha256(schema).hexdigest()},
    }))
    return tmp_path


XML = '<OpenSCENARIO><FileHeader revMajor="1" revMinor="2"/><RequiredBody/></OpenSCENARIO>'


def test_declared_version_and_diagnostics_are_separate_from_well_formedness(tmp_path):
    root = registry(tmp_path)
    valid = validate_xml(XML, root=root)
    assert valid["status"] == "valid"
    assert valid["version"] == "1.2"
    assert valid["source_revision"] == "authored"
    manifest = json.loads((root / "registry.json").read_text())
    assert valid["schema_sha256"] == manifest["sha256"]["authored.xsd"]
    assert valid["registry_sha256"] != valid["schema_sha256"]
    invalid = validate_xml(XML.replace("<RequiredBody/>", ""), root=root)
    assert invalid["status"] == "invalid"
    assert invalid["issues"][0]["line"] == 1
    unknown = validate_xml(XML.replace('revMinor="2"', 'revMinor="9"'), root=root)
    assert unknown["status"] == "unsupported"
    assert validate_xml(XML, root=tmp_path / "missing")["status"] == "unavailable"


def test_corrupt_schema_and_dtd_never_claim_validity(tmp_path):
    registry(tmp_path)
    (tmp_path / "authored.xsd").write_text("corrupt")
    result = validate_xml(XML, root=tmp_path)
    assert result["status"] == "unavailable"
    assert "integrity" in result["detail"]
    assert validate_xml('<!DOCTYPE OpenSCENARIO [<!ENTITY x "value">]>' + XML, root=tmp_path)["status"] == "invalid"


def test_local_schema_includes_and_external_reference_rejection(tmp_path):
    registry(tmp_path)
    main = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="authored.xsd"/></xs:schema>'
    (tmp_path / "main.xsd").write_bytes(main)
    manifest = json.loads((tmp_path / "registry.json").read_text())
    manifest["entries"]["OpenSCENARIO:1.2"] = "main.xsd"
    manifest["sha256"]["main.xsd"] = hashlib.sha256(main).hexdigest()
    (tmp_path / "registry.json").write_text(json.dumps(manifest))
    assert validate_xml(XML, root=tmp_path)["status"] == "valid"
    manifest["entries"]["OpenSCENARIO:1.2"] = "../outside.xsd"
    (tmp_path / "registry.json").write_text(json.dumps(manifest))
    assert validate_xml(XML, root=tmp_path)["status"] == "unavailable"


def test_xsd11_assertion_is_enforced_and_untrusted_includes_fail(tmp_path):
    registry(tmp_path)
    path = tmp_path / "authored.xsd"
    schema = path.read_bytes().replace(
        b'</xs:sequence></xs:complexType></xs:element>',
        b'</xs:sequence><xs:assert test="FileHeader/@revMinor = 2"/></xs:complexType></xs:element>',
    )
    path.write_bytes(schema)
    manifest = json.loads((tmp_path / "registry.json").read_text())
    manifest["entries"]["OpenSCENARIO:1.3"] = "authored.xsd"
    manifest["xsd_versions"] = {"OpenSCENARIO:1.2": "1.1", "OpenSCENARIO:1.3": "1.1"}
    manifest["sha256"]["authored.xsd"] = hashlib.sha256(schema).hexdigest()
    (tmp_path / "registry.json").write_text(json.dumps(manifest))
    assert validate_xml(XML, root=tmp_path)["status"] == "valid"
    invalid = validate_xml(XML.replace('revMinor="2"', 'revMinor="3"'), root=tmp_path)
    assert invalid["status"] == "invalid"
    assert "assertion" in invalid["issues"][0]["message"]
    for location in ("https://example.com/schema.xsd", "../outside.xsd", "missing.xsd"):
        schema = f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="{location}"/></xs:schema>'.encode()
        path.write_bytes(schema)
        manifest["sha256"]["authored.xsd"] = hashlib.sha256(schema).hexdigest()
        (tmp_path / "registry.json").write_text(json.dumps(manifest))
        assert validate_xml(XML, root=tmp_path)["status"] == "unavailable"
