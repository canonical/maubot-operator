import pytest
import os
import ast

EVENTS = ["config_changed"]  # expand this list

def get_test_functions(test_dir="tests/unit"):
    test_names = set()
    for fname in os.listdir(test_dir):
        if fname.startswith("test_") and fname.endswith(".py"):
            with open(os.path.join(test_dir, fname)) as f:
                tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        test_names.add(node.name)
    return test_names

def test_event_handlers_are_tested():
    test_names = get_test_functions()
    missing = []
    for event in EVENTS:
        expected_prefix = f"test_{event}"
        if not any(expected_prefix in name for name in test_names):
            missing.append(event)
    assert not missing, f"Missing tests for: {', '.join(missing)}"
