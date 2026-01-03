import shlex
import sys

import toolbox.tool_parser as tool_parser


def test_build_command_from_action_fields_adds_threads_and_quotes_paths():
    action = {
        "id": "scan",
        "fields": [
            {"id": "directory", "type": "directory"},
            {"id": "hash", "type": "select"},
        ],
    }

    cmd = tool_parser.build_command_from_action(
        tool_id="hashdb",
        action=action,
        field_values={"directory": "/tmp/has space", "hash": "sha256"},
        python_exe=sys.executable,
        threads=3,
    )

    parts = shlex.split(cmd)
    assert parts[0] == sys.executable
    assert parts[1].endswith("toolbox.py")
    assert "hashdb" in parts

    # directory is positional for common fields
    assert "/tmp/has space" in parts

    # hash should be flagged
    assert "--hash" in parts
    assert parts[parts.index("--hash") + 1] == "sha256"

    # threads are appended
    assert "--threads" in parts
    assert parts[parts.index("--threads") + 1] == "3"


def test_build_command_from_action_template_expands_placeholders_and_adds_threads():
    action = {
        "id": "verify",
        "command": "hashdb verify --db {database}",
        "fields": [
            {"id": "database", "type": "file"},
        ],
    }

    cmd = tool_parser.build_command_from_action(
        tool_id="hashdb",
        action=action,
        field_values={"database": "./my db.sqlite"},
        python_exe=sys.executable,
        threads=5,
    )

    parts = shlex.split(cmd)
    assert parts[0] == sys.executable
    assert "hashdb" in parts
    assert "verify" in parts

    # placeholder should be filled and quoted correctly
    assert "--db" in parts
    assert parts[parts.index("--db") + 1] == "./my db.sqlite"

    assert "--threads" in parts
    assert parts[parts.index("--threads") + 1] == "5"
