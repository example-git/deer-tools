"""Smoke tests for Deer Toolbox after reorg.

These tests validate imports and basic discovery without requiring optional deps.
"""


def test_toolbox_module_imports():
    import toolbox.webui as webui
    import toolbox.textui as textui
    import toolbox.desktopui as desktopui
    import toolbox.tui as tui
    import toolbox.tool_parser as tool_parser

    assert webui is not None
    assert textui is not None
    assert desktopui is not None
    assert tui is not None
    assert tool_parser is not None


def test_shared_public_api_imports():
    from shared import (
        load_persistent_config,
        save_persistent_config,
        get_config_dir,
        merge_settings,
        build_settings,
        iter_files,
        BaseWorker,
        LogWatcher,
    )

    assert callable(load_persistent_config)
    assert callable(save_persistent_config)
    assert callable(get_config_dir)
    assert callable(merge_settings)
    assert callable(build_settings)
    assert callable(iter_files)
    assert BaseWorker is not None
    assert LogWatcher is not None


def test_tool_parser_discovers_builtin_plugins():
    import toolbox.tool_parser as tool_parser

    tools = tool_parser.discover_tools()
    assert isinstance(tools, dict)

    # These are part of this repo; discovery should find them.
    expected = {"extension_repair", "hashdb", "undo_transfer"}
    assert expected.issubset(set(tools.keys()))


def test_plugin_tool_modules_import_and_expose_run():
    import plugins.extension_repair.tool as extension_repair_tool
    import plugins.hashdb.tool as hashdb_tool
    import plugins.undo_transfer.tool as undo_transfer_tool

    assert hasattr(extension_repair_tool, "run")
    assert hasattr(hashdb_tool, "run")
    assert hasattr(undo_transfer_tool, "run")
