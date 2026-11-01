import pytest
from pydantic import ValidationError

from anvil.workspace_environments import Environment
from anvil.workspace_preparation import Preparation


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/absolute",
        "inputs/../../escape",
        ".env",
        "inputs/.secret",
        "inputs//file",
        "inputs\\file",
        "inputs/./file",
    ],
)
def test_context_paths_cannot_escape_or_include_hidden_files(path):
    with pytest.raises(ValidationError):
        Environment(
            name="test",
            files=[
                {"path": "Dockerfile", "content": "FROM example"},
                {"path": path, "content": "test"},
            ],
        )


def test_environment_requires_dockerfile_unique_paths_and_bounded_text():
    for files in (
        [{"path": "inputs/test.txt", "content": "test"}],
        [{"path": "Dockerfile", "content": "FROM example"}] * 2,
        [{"path": "Dockerfile", "content": "a" * 262145}],
    ):
        with pytest.raises(ValidationError):
            Environment(name="test", files=files)
    assert (
        Environment(
            name="test",
            files=[
                {"path": "Dockerfile", "content": "FROM example"},
                {"path": "inputs/test.txt", "content": "test"},
            ],
        )
        .files[1]
        .path
        == "inputs/test.txt"
    )


@pytest.mark.parametrize("trials", [True, 0, 11, 1.5])
def test_repetition_limits_are_strict(trials):
    with pytest.raises(ValidationError):
        Preparation(
            preset_id="00000000-0000-4000-8000-000000000001",
            package_id="00000000-0000-4000-8000-000000000002",
            model_profile_ids=["00000000-0000-4000-8000-000000000003"],
            max_output_tokens=1024,
            episode_timeout_seconds=300,
            trials_per_model=trials,
        )
