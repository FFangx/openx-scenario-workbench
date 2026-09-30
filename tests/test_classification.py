import io
import json
from pathlib import Path

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.classification import classify_asset, confirm_classification, read_classification
from openx_workbench.llm_service import ModelClient, ModelConfig


def test_asset_classification_keeps_bytes_and_rule_model_manual_history(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    store = AssetStore(tmp_path)
    version = store.import_files([AssetFile(name, (fixtures / name).read_bytes()) for name in ("minimal.xosc", "minimal.xodr")])[0]
    original = store.file_bytes(version, "scenario")
    classification = {"function_type": "AEB", "label_road_type": "直道", "label_target_type": ["乘用车"],
                      "label_actions": ["制动"], "scenario_intent": "Brake before a target", "confidence": .91, "reason": "Authored fixture"}
    def opener(request, timeout):
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(classification)}}]}).encode())
    client = ModelClient(ModelConfig(api_key="authored"), opener=opener)
    result = classify_asset(store, version, use_model=True, client=client)
    assert result["status"] == "classified"
    assert result["final"]["function_type"] == "AEB"
    assert result["llm"]["confidence"] == .91
    confirmed = confirm_classification(store, version, {**result["final"], "function_type": "ACC"})
    assert confirmed["status"] == "manual_confirmed"
    assert confirmed["llm"] == result["llm"]
    assert read_classification(store, version)["final"]["function_type"] == "ACC"
    assert store.file_bytes(version, "scenario") == original
    assert len(list((tmp_path / "assets").glob("*/*/classification_history/*.json"))) == 2
    classification["function_type"] = "invented-function"
    result = classify_asset(store, version, use_model=True, client=client)
    assert result["status"] == "failed"
    assert result["final"] == confirmed["final"]
    assert result["fallback_source"] == "previous_classification"
