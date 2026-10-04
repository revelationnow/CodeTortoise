"""Repeated edits: line pairs whose only difference is one run of tokens (spec 2026-10-04-change-stories §2.1)."""
from codetortoise.substitutions import Site, Sub, changed_pairs, explained, substitution, tokens


def test_tokens_skip_comments_and_whitespace():
    assert tokens('  x->size = f(a, "s, t"); // note') == ["x", "->", "size", "=", "f", "(", "a", ",", '"s, t"', ")", ";"]
    assert tokens("a /* gone */ + b") == ["a", "+", "b"]


def test_a_substitution_is_one_run_of_tokens_that_differs():
    assert substitution("\tgit_vector_free(&v);", "\tgit_vector_dispose(&v);") == Sub("git_vector_free", "git_vector_dispose")
    assert substitution("return -1;", "return GIT_EINVALID;") == Sub("- 1", "GIT_EINVALID")
    assert substitution("int n = len(x);", "size_t n = len(x);") == Sub("int", "size_t")


def test_lines_differing_in_two_places_or_by_an_insertion_are_not_substitutions():
    assert substitution("f(a, b);", "g(a, c);") is None
    assert substitution("f(a);", "f(a, b);") is None             # a token inserted
    assert substitution("f(a);", "  f(a);  // same") is None      # no token differs


def test_a_function_is_explained_only_when_every_changed_line_is_a_substitution():
    before = ["void f(void) {", "  git_vector_free(&a);", "  x = 1;", "  git_vector_free(&b);", "}"]
    after = ["void f(void) {", "  git_vector_dispose(&a);", "  x = 1;", "  git_vector_dispose(&b);", "}"]
    sites = explained(before, after)
    assert [(s.sub, s.before_line, s.after_line) for s in sites] == [
        (Sub("git_vector_free", "git_vector_dispose"), 2, 2), (Sub("git_vector_free", "git_vector_dispose"), 4, 4)]
    assert sites[0].before == "git_vector_free(&a);" and sites[0].after == "git_vector_dispose(&a);"
    other = after[:3] + ["  y = 2;"] + after[3:]                  # one more line added: not explained
    assert explained(before, other) is None
    sites, unexplained = changed_pairs(before, other)
    assert len(sites) == 1 and unexplained == 3        # the unequal hunk's lines


def test_unequal_hunks_and_whitespace_only_changes():
    assert explained(["a;", "b;"], ["c;"]) is None
    assert explained(["  f(x);"], ["\tf(x);"]) is None            # nothing substituted: not a repeated edit
    assert explained(["  f(x);", "g(1);"], ["\tf(x);", "g(2);"]) == [Site(Sub("1", "2"), 2, 2, "g(1);", "g(2);")]
