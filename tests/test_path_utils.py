from pathlib import Path
from typing import cast

from shared.path_utils import next_nonconflicting_path, safe_rename


def test_next_nonconflicting_path_returns_original_if_free(tmp_path):
    p = tmp_path / "file.txt"
    out = next_nonconflicting_path(str(p))
    assert out == str(p)


def test_next_nonconflicting_path_adds_suffix_if_exists(tmp_path):
    p = tmp_path / "file.txt"
    p.write_text("x", encoding="utf-8")

    out = next_nonconflicting_path(str(p))
    assert out != str(p)
    assert Path(out).name.startswith("file_")
    assert Path(out).suffix == ".txt"


def test_safe_rename_never_overwrites_existing(tmp_path):
    old_path = tmp_path / "old.txt"
    old_path.write_text("old", encoding="utf-8")

    target = tmp_path / "target.txt"
    target.write_text("existing", encoding="utf-8")

    status, final_target = safe_rename(str(old_path), str(target))
    assert status == "ok"
    assert final_target is not None

    # Narrow type for static type checkers: safe_rename may return an Exception on failure.
    assert not isinstance(final_target, Exception)

    final_path = Path(cast(str, final_target))
    assert final_path.exists()
    assert final_path.read_text(encoding="utf-8") == "old"

    # original target should be untouched
    assert target.read_text(encoding="utf-8") == "existing"
