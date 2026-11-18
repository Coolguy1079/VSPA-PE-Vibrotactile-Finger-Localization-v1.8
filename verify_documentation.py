#!/usr/bin/env python3
"""Verify that documentation edits preserve v1.8 executable acquisition logic.

Run from the repository root:
    python3 verify_documentation.py --json documentation_equivalence.json

This is an offline source check. It does not run the GUI, open a serial port,
compile Arduino firmware, or claim physical validation. The exact source
snapshot is pinned to commit 6041d4adc8f4c507671996160b7b0f3a439b69ef.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import platform
import re
import tokenize
from pathlib import Path

SOURCE_COMMIT = "6041d4adc8f4c507671996160b7b0f3a439b69ef"
ARCHIVE = Path("archive/acquisition_v1_8")
FIRMWARE = Path("firmware/firmware_vspa_rtp_v1_5/firmware_vspa_rtp_v1_5.ino")
ORIGINAL_FIRMWARE_SHA256 = "80ed2073bf716c7eb4119e36874482bf187c2f0f37aabadc7f22a3d2b9b1bea0"
PRODUCTION_PYTHON = (
    "vspa_protocol.py", "self_test_gui_v1_8.py", "analyze_timing.py", "diagnose_arduino.py",
)
ALLOWED_DOCSTRING_CHANGES = {
    "vspa_protocol.py": {"<module>", "ProtocolConfig", "build_schedule"},
    "analyze_timing.py": {"<module>"},
    "self_test_gui_v1_8.py": set(),
    "diagnose_arduino.py": set(),
}
# These constants pin the archive independently of its human-readable manifest.
ORIGINAL_SHA256 = {
    "CHANGELOG_v1_8.md": "d3efbab49dda6811e5ae619a14ef0f0c77e598ecaf452e50151e79960c47d894",
    "README.md": "03fac023a7a096b16ba5732aef0b9a78c3b304c9216ea8ea97d8e8ef851fad0a",
    "SCHEDULE_PREVIEW_NOT_RESEARCH_DATA.csv": "3fe7e2f2279dc69b3049a1936815d5a3511ac9f0170c1f4865c714c18eb7cbc8",
    "START_HERE.txt": "2f08ccab7ab0aa8112a98c871cda7b955a556293df6242ae7c63ddfb43e98244",
    "analyze_timing.py": "662e9d341aafebbb718b18fb098ae5d2bc4b6c0ea8b77423ea0cde640406d917",
    "baseline_v1_6/analyze_sessions_v1_6.py": "91df18fe72f8c14385ca116d35c184e46be9e6f6703b19d0415b3ffcdc322d73",
    "baseline_v1_6/self_test_gui_v1_6.py": "fe993d2b6f64622b7adaf49646aff776faccf026884c8e4743ddcd1f0fb3c27c",
    "baseline_v1_6/vspa_protocol.py": "9b21d6182b8ed8c3ef4378a7ff2abae97f055022eaaea04a155e177f76154655",
    "diagnose_arduino.py": "b7b62947f644d04ebb4863dca9cb052d349bac5c1e66196d1900cb8f070950a7",
    FIRMWARE.as_posix(): ORIGINAL_FIRMWARE_SHA256,
    "requirements.txt": "95fdad543f34e4a191cd17219e1a73b4ab4b0b5ad9806a25c3b49e7b48ab8ca0",
    "self_test_gui_v1_8.py": "4cfa2efc6e858f05894f947506d1042ae8bfefb8be74597659955e24e1f53ab5",
    "tests/test_serial_timing.py": "024dd9ebf90c78e55afd4d77979161f38243d07cbb3e4db59c16e1bd8deccabf",
    "tests/test_v1_8.py": "7803803d9722e1e96647932f23458c1202168d48898ab1098d7756b43911fb22",
    "vspa_protocol.py": "09dc861fda7142cc9f45ebc398e8c82dd99e48f10b3583c7ed7870ac33e79a8b",
}


# Hash the actual byte stream, including comments, for provenance comparisons.
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Locate only syntactic module/class/function docstrings, never arbitrary string literals.
def docstring_nodes(tree: ast.AST) -> dict[str, ast.Expr]:
    found = {}

    # Carry lexical names so the report identifies each intentional __doc__ change.
    def walk(node: ast.AST, names: tuple[str, ...]) -> None:
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found[".".join(names) or "<module>"] = node.body[0]
        for child in ast.iter_child_nodes(node):
            child_names = (*names, child.name) if isinstance(
                child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else names
            walk(child, child_names)

    walk(tree, ())
    return found


# Normalize comments/locations automatically through AST parsing; optionally omit docstrings only.
def python_ast(source: str, *, omit_docstrings: bool = False, class_name: str | None = None) -> str:
    tree = ast.parse(source)
    if omit_docstrings:
        targets = {id(node) for node in docstring_nodes(tree).values()}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                node.body = [statement for statement in node.body if id(statement) not in targets]
    if class_name is not None:
        matches = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one top-level class named {class_name}")
        tree = matches[0]
    return ast.dump(tree, include_attributes=False)


# Compare executable Python tokens independently of the AST, preserving all non-docstring literals.
def python_tokens(source: str, *, omit_docstrings: bool = False, class_name: str | None = None) -> list:
    if class_name is not None:
        tree = ast.parse(source)
        matches = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one top-level class named {class_name}")
        source = ast.get_source_segment(source, matches[0])
    spans = []
    if omit_docstrings:
        spans = [((node.lineno, node.col_offset), (node.end_lineno, node.end_col_offset))
                 for node in docstring_nodes(ast.parse(source)).values()]
    ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.ENCODING}
    result = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in ignored:
            continue
        if token.type == tokenize.STRING and any(start <= token.start and token.end <= end for start, end in spans):
            continue
        result.append((token.type, token.string))
    return result


# Tokenize this sketch's C++ syntax while protecting string/character literals from comment removal.
def firmware_tokens(source: str) -> list:
    """Return non-comment tokens; preserve preprocessing-line boundaries.

    This lexer covers the existing sketch, including quoted strings, decimal/
    hexadecimal numbers and multicharacter operators. It is a source-equivalence
    check, not an Arduino compiler. Unsupported raw string literals fail closed.
    """
    if re.search(r'(?:u8|u|U|L)?R"', source):
        raise ValueError("Raw C++ strings are not supported by this verification lexer")
    pattern = re.compile(
        r'(?P<space>\s+)|(?P<comment>//[^\n]*|/\*.*?\*/)|'
        r'(?P<literal>(?:u8|u|U|L)?"(?:\\.|[^"\\])*"|(?:u8|u|U|L)?\'(?:\\.|[^\'\\])*\')|'
        r'(?P<identifier>[A-Za-z_]\w*)|'
        r'(?P<number>(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d*)?(?:[eEpP][+-]?\d+)?)[uUlLfF]*)|'
        r'(?P<operator><<=|>>=|->\*|\.\.\.|::|\+\+|--|->|\.\*|<<|>>|<=|>=|==|!=|&&|\|\||'
        r'\+=|-=|\*=|/=|%=|\^=|&=|\|=|##|.)', re.DOTALL)
    result = []
    directive = False
    for match in pattern.finditer(source):
        kind, value = match.lastgroup, match.group()
        if kind in {"space", "comment"}:
            if directive and "\n" in value:
                result.append(("directive_end", "\n"))
                directive = False
            continue
        result.append((kind, value))
        if value == "#":
            directive = True
    if directive:
        result.append(("directive_end", "\n"))
    return result


# Raise on an invariant violation and return a reviewable comparison report on success.
def verify(root: Path) -> dict:
    archive = root / ARCHIVE
    preserved = []
    for relative, expected in ORIGINAL_SHA256.items():
        observed = sha256((archive / relative).read_bytes())
        if observed != expected:
            raise AssertionError(f"Frozen source hash mismatch: {relative}")
        preserved.append({"path": relative, "sha256": observed})

    python_reports = []
    for relative in PRODUCTION_PYTHON:
        before = (archive / relative).read_text(encoding="utf-8")
        after = (root / relative).read_text(encoding="utf-8")
        old_docs, new_docs = docstring_nodes(ast.parse(before)), docstring_nodes(ast.parse(after))
        changed_docs = []
        for name in sorted(set(old_docs) | set(new_docs)):
            old_text = ast.literal_eval(old_docs[name].value) if name in old_docs else None
            new_text = ast.literal_eval(new_docs[name].value) if name in new_docs else None
            if old_text != new_text:
                changed_docs.append({"name": name, "original": old_text, "documented": new_text})
        if {item["name"] for item in changed_docs} != ALLOWED_DOCSTRING_CHANGES[relative]:
            raise AssertionError(f"Unexpected docstring changes: {relative}")
        old_ast, new_ast = python_ast(before, omit_docstrings=True), python_ast(after, omit_docstrings=True)
        if old_ast != new_ast:
            raise AssertionError(f"Executable Python AST changed: {relative}")
        if python_tokens(before, omit_docstrings=True) != python_tokens(after, omit_docstrings=True):
            raise AssertionError(f"Non-comment/non-docstring Python tokens changed: {relative}")
        python_reports.append({
            "path": relative, "original_sha256": sha256(before.encode()), "documented_sha256": sha256(after.encode()),
            "full_ast_identical": python_ast(before) == python_ast(after),
            "ast_identical_except_docstrings": True, "executable_tokens_identical": True,
            "normalized_ast_sha256": sha256(old_ast.encode()), "intentional_docstring_changes": changed_docs,
        })

    baseline_transport = (root / "baseline_v1_6/vspa_protocol.py").read_text(encoding="utf-8")
    documented_transport = (root / "vspa_protocol.py").read_text(encoding="utf-8")
    if python_ast(baseline_transport, class_name="HapticDevice") != python_ast(documented_transport, class_name="HapticDevice"):
        raise AssertionError("HapticDevice AST differs from the retained v1.6 transport")
    if python_tokens(baseline_transport, class_name="HapticDevice") != python_tokens(documented_transport, class_name="HapticDevice"):
        raise AssertionError("HapticDevice tokens differ from the retained v1.6 transport")
    for relative, expected in ORIGINAL_SHA256.items():
        if relative.startswith("baseline_v1_6/") and sha256((root / relative).read_bytes()) != expected:
            raise AssertionError(f"Protected v1.6 baseline changed: {relative}")

    original_firmware = (archive / FIRMWARE).read_text(encoding="utf-8")
    documented_firmware = (root / FIRMWARE).read_text(encoding="utf-8")
    original_tokens, documented_tokens = firmware_tokens(original_firmware), firmware_tokens(documented_firmware)
    if original_tokens != documented_tokens:
        raise AssertionError("Firmware executable tokens changed")
    return {
        "source_commit": SOURCE_COMMIT, "python_version": platform.python_version(),
        "archive_files_verified": len(preserved), "archive": preserved,
        "production_python": python_reports,
        "haptic_device_ast_identical_to_v1_6": True,
        "haptic_device_tokens_identical_to_v1_6": True,
        "baseline_v1_6_bytes_unchanged": True,
        "firmware": {"path": FIRMWARE.as_posix(), "original_sha256": ORIGINAL_FIRMWARE_SHA256,
                     "documented_sha256": sha256(documented_firmware.encode()),
                     "non_comment_tokens_identical": True, "token_count": len(original_tokens),
                     "tokens_sha256": sha256(json.dumps(original_tokens, separators=(",", ":")).encode())},
        "physical_hardware_verified": False,
        "scope": "Executable source equivalence; comments, four corrected __doc__ strings and source-byte provenance differ.",
        "observable_documentation_changes": [
            "Corrected __doc__ text, including analyze_timing.py --help description.",
            "Source line numbers and future files_sha256 metadata reflect the documented source bytes.",
        ],
    }


# Offer a standalone source audit without importing the GUI or acquiring any data.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Write the detailed proof report to this path")
    args = parser.parse_args()
    report = verify(Path(__file__).resolve().parent)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {report['archive_files_verified']} frozen files, four Python modules, "
          "v1.6 transport equivalence and firmware non-comment tokens.")
    print("No physical Arduino, actuator or native macOS GUI test was performed.")


if __name__ == "__main__":
    main()
