import pytest

from bridge.prompts import OutputDirCancelled, choose_output_dir, validate_output_dir


def test_validate_existing_writable_dir(tmp_path):
    result = validate_output_dir(tmp_path)
    assert result == tmp_path.resolve()


def test_validate_rejects_file(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(ValueError, match="Not a directory"):
        validate_output_dir(f)


def test_validate_create_missing(tmp_path):
    target = tmp_path / "new_dir"
    result = validate_output_dir(target, create=True)
    assert result.is_dir()


def test_choose_output_dir_with_injected_prompt(tmp_path):
    path = choose_output_dir(prompt_fn=lambda: str(tmp_path))
    assert path.resolve() == tmp_path.resolve()


def test_choose_output_dir_cancelled():
    with pytest.raises(OutputDirCancelled):
        choose_output_dir(prompt_fn=lambda: None)
