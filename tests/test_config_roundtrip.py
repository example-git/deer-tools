from shared.config import (
    build_settings,
    load_persistent_config,
    merge_settings,
    save_persistent_config,
)


def test_persistent_config_roundtrip(tmp_path):
    config_name = "test.json"
    data = {"a": 1, "b": "two"}

    ok = save_persistent_config(data, config_name=config_name, config_dir=tmp_path)
    assert ok is True

    loaded = load_persistent_config(config_name=config_name, config_dir=tmp_path)
    assert loaded == data


def test_merge_settings_respects_override_precedence():
    merged = merge_settings(
        defaults={"a": 1, "b": 2},
        persistent={"b": 3, "c": 4},
        overrides={"b": 5, "d": 6},
    )
    assert merged == {"a": 1, "b": 5, "c": 4, "d": 6}


def test_build_settings_combines_defaults_persistent_and_cli(tmp_path):
    # persistent wins over defaults, cli wins over persistent
    save_persistent_config({"threads": 4, "mode": "persisted"}, config_name="cfg.json", config_dir=tmp_path)

    result = build_settings(
        cli_args={"threads": 8},
        config_name="cfg.json",
        config_dir=tmp_path,
        defaults={"threads": 2, "mode": "default"},
    )

    assert result["threads"] == 8
    assert result["mode"] == "persisted"
