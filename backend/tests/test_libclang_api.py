"""libclang C API calls that don't depend on private parts of the Python bindings (they changed after 18)."""
import clang.cindex as ci

from codetortoise.toolchain import libclang


def test_version_and_operator_spelling_without_private_bindings(monkeypatch):
    libclang.load_libclang(None)
    monkeypatch.delattr(ci, "_CXString", raising=False)         # absent or changed in newer bindings
    assert "clang version" in libclang._version()
    from codetortoise.facts import aliasflow
    monkeypatch.setattr(aliasflow, "_capi", None)
    api = aliasflow._c_api()
    assert api["bin_spell"] is not None and api["bin_spell"](22) == "="           # CXBinaryOperator_Assign


def test_unknown_cursor_and_type_kinds_read_as_unexposed():
    libclang.load_libclang(None)                                  # installs the tolerance
    assert ci.CursorKind.from_id(9999) == ci.CursorKind.UNEXPOSED_EXPR
    assert ci.TypeKind.from_id(9999) == ci.TypeKind.UNEXPOSED
    assert ci.CursorKind.from_id(ci.CursorKind.CALL_EXPR.value) == ci.CursorKind.CALL_EXPR
