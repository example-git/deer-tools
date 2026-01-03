import json
from pathlib import Path


def test_all_plugin_metadata_json_is_valid_and_has_required_fields():
    repo_root = Path(__file__).resolve().parents[1]
    plugins_dir = repo_root / "plugins"
    assert plugins_dir.is_dir()

    required_str_fields = {"id", "name", "version", "description"}

    for tool_dir in sorted(
        p
        for p in plugins_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("__")
    ):
        meta_path = tool_dir / "metadata.json"
        assert meta_path.exists(), f"Missing metadata.json in {tool_dir.name}"

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert isinstance(meta, dict)

        for key in required_str_fields:
            assert key in meta, f"{tool_dir.name}: missing '{key}'"
            assert isinstance(meta[key], str) and meta[key].strip(), f"{tool_dir.name}: '{key}' must be a non-empty string"

        # Basic sanity: ids should not contain spaces
        assert " " not in meta["id"], f"{tool_dir.name}: id should not contain spaces"
