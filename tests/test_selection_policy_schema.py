"""Deterministic tests for the selection-policy semantic schema."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
import inspect
import json

import pytest

import dsh_runtime.selection_policy_schema as schema_module
from dsh_runtime.policy_artifact_loader import LoadedPolicyArtifact, load_policy_artifact
from dsh_runtime.selection_policy_schema import (
    LoadedSelectionPolicy,
    SelectionPolicyContentValidationError,
    SelectionPolicySchemaError,
    SelectionPolicyWorkloadValidationError,
    ValidatedSelectionPolicySemantics,
    parse_selection_policy_semantics,
)


@dataclass(frozen=True)
class InMemoryPolicyArtifactSource:
    document: str

    def read_text(self) -> str:
        return self.document


def _loaded(policy_content: object) -> LoadedPolicyArtifact:
    document = json.dumps(
        {
            "policy_id": "selection-policy-candidate",
            "policy_version": "candidate-1",
            "artifact_schema_version": "1",
            "policy_content": policy_content,
        }
    )
    return load_policy_artifact(InMemoryPolicyArtifactSource(document))


def test_valid_one_workload_semantics() -> None:
    parsed = parse_selection_policy_semantics(
        _loaded({"authorized_workloads": ["repository_change"]})
    )

    assert isinstance(parsed, LoadedSelectionPolicy)
    assert parsed.semantics.authorized_workloads == frozenset(
        {"repository_change"}
    )


def test_multiple_workloads_are_represented_without_authorizing_them() -> None:
    parsed = parse_selection_policy_semantics(
        _loaded(
            {
                "authorized_workloads": [
                    "repository_change",
                    "repository_inspection",
                ]
            }
        )
    )

    assert parsed.semantics.authorized_workloads == frozenset(
        {"repository_change", "repository_inspection"}
    )


def test_empty_workload_set_is_valid() -> None:
    parsed = parse_selection_policy_semantics(
        _loaded({"authorized_workloads": []})
    )

    assert parsed.semantics.authorized_workloads == frozenset()


def test_missing_authorized_workloads_is_rejected() -> None:
    with pytest.raises(
        SelectionPolicyContentValidationError,
        match="missing.*authorized_workloads",
    ):
        parse_selection_policy_semantics(_loaded({}))


@pytest.mark.parametrize(
    "authorized_workloads",
    [None, "repository_change", {"repository_change": True}, 1],
)
def test_invalid_workload_collection_is_rejected(
    authorized_workloads: object,
) -> None:
    with pytest.raises(
        SelectionPolicyWorkloadValidationError,
        match="JSON array",
    ):
        parse_selection_policy_semantics(
            _loaded({"authorized_workloads": authorized_workloads})
        )


@pytest.mark.parametrize("identifier", ["", "   ", None, 1])
def test_invalid_workload_identifier_is_rejected(identifier: object) -> None:
    with pytest.raises(
        SelectionPolicyWorkloadValidationError,
        match="non-empty strings",
    ):
        parse_selection_policy_semantics(
            _loaded({"authorized_workloads": [identifier]})
        )


def test_duplicate_workload_identifier_is_rejected() -> None:
    with pytest.raises(
        SelectionPolicyWorkloadValidationError,
        match="duplicate.*repository_change",
    ):
        parse_selection_policy_semantics(
            _loaded(
                {
                    "authorized_workloads": [
                        "repository_change",
                        "repository_change",
                    ]
                }
            )
        )


def test_unknown_semantic_field_is_rejected() -> None:
    with pytest.raises(
        SelectionPolicyContentValidationError,
        match="unexpected.*secret_override",
    ):
        parse_selection_policy_semantics(
            _loaded(
                {
                    "authorized_workloads": ["repository_change"],
                    "secret_override": True,
                }
            )
        )


def test_semantic_result_is_immutable_and_detached_from_source() -> None:
    source_workloads = ["repository_change"]
    loaded = _loaded({"authorized_workloads": source_workloads})
    parsed = parse_selection_policy_semantics(loaded)

    source_workloads.append("repository_inspection")

    assert parsed.semantics.authorized_workloads == frozenset(
        {"repository_change"}
    )
    with pytest.raises(FrozenInstanceError):
        parsed.semantics.authorized_workloads = frozenset()  # type: ignore[misc]


def test_artifact_identity_is_preserved_without_recreation() -> None:
    loaded = _loaded({"authorized_workloads": ["repository_change"]})

    parsed = parse_selection_policy_semantics(loaded)

    assert parsed.policy_identity is loaded.identity


def test_parser_api_has_no_authorization_inputs() -> None:
    signature = inspect.signature(parse_selection_policy_semantics)

    assert tuple(signature.parameters) == ("loaded_artifact",)
    assert not {
        "proposal",
        "trusted_context",
        "session_pin",
        "enabled_workloads",
        "goal",
        "caller_id",
    }.intersection(signature.parameters)


def test_schema_module_has_no_runtime_gate_or_session_dependency() -> None:
    tree = ast.parse(inspect.getsource(schema_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not {
        "controller",
        "planner",
        "entrypoint",
        "gate_contract",
        "session_policy_pin",
        "runtime",
    }.intersection(imported_modules)


def test_semantic_failures_are_distinct_from_artifact_load_failures() -> None:
    with pytest.raises(SelectionPolicySchemaError):
        parse_selection_policy_semantics(
            _loaded({"authorized_workloads": ["", "repository_change"]})
        )


def test_raw_policy_content_cannot_bypass_loading_boundary() -> None:
    with pytest.raises(
        SelectionPolicyContentValidationError,
        match="LoadedPolicyArtifact",
    ):
        parse_selection_policy_semantics(  # type: ignore[arg-type]
            {"authorized_workloads": ["repository_change"]}
        )


def test_semantic_model_freezes_external_collections() -> None:
    workloads = ["repository_change"]
    semantics = ValidatedSelectionPolicySemantics(workloads)

    workloads.append("repository_inspection")

    assert semantics.authorized_workloads == frozenset({"repository_change"})
