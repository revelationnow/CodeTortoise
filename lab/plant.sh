#!/usr/bin/env bash
# Creates three shelved CLs with planted side effects, leaving the workspace clean at head.
set -euo pipefail
LAB=${LAB:?set LAB to the lab directory}
source "$LAB/env.sh"
cd $LAB/ws
newcl() { p4 change -o | sed "s#<enter description here>#$1#" | p4 change -i | grep -oE '[0-9]+'; }

# CL A: new return value from output_eol
A=$(newcl "crlf: honour core.eol=native in output_eol")
p4 edit -c $A src/libgit2/crlf.c >/dev/null
python3 - <<'PY'
p='src/libgit2/crlf.c'; s=open(p).read()
old="\t/* TODO: warn when available */\n\treturn ca->core_eol;"
new="\tif (ca->core_eol == GIT_EOL_NATIVE)\n\t\treturn GIT_EOL_NATIVE;\n\n\t/* TODO: warn when available */\n\treturn ca->core_eol;"
assert old in s; open(p,'w').write(s.replace(old,new))
PY
p4 shelve -c $A >/dev/null && p4 revert -c $A //... >/dev/null

# CL B: getter invalidates the config cache through a local alias
B=$(newcl "repository: refresh autocrlf when checking detached HEAD")
p4 edit -c $B src/libgit2/repository.c >/dev/null
python3 - <<'PY'
p='src/libgit2/repository.c'; s=open(p).read()
old="\tif (git_repository_odb__weakptr(&odb, repo) < 0)\n\t\treturn -1;\n\n\tif (git_reference_lookup(&ref, repo, GIT_HEAD_REF) < 0)"
new=("\tintptr_t *cache = repo->configmap_cache;\n\n"
     "\tif (git_repository_odb__weakptr(&odb, repo) < 0)\n\t\treturn -1;\n\n"
     "\t/* HEAD may have moved to a branch with different line endings */\n"
     "\tcache[GIT_CONFIGMAP_AUTO_CRLF] = GIT_CONFIGMAP_NOT_CACHED;\n\n"
     "\tif (git_reference_lookup(&ref, repo, GIT_HEAD_REF) < 0)")
assert s.count(old) == 1; open(p,'w').write(s.replace(old,new))
PY
cp src/libgit2/repository.c /tmp/lab-repo-B.c
p4 shelve -c $B >/dev/null && p4 revert -c $B //... >/dev/null

# CL C (stacked on B): struct layout change + alias write of the new field
C=$(newcl "repository: cache detached HEAD state")
p4 edit -c $C src/libgit2/repository.c src/libgit2/repository.h >/dev/null
cp /tmp/lab-repo-B.c src/libgit2/repository.c
python3 - <<'PY'
p='src/libgit2/repository.h'; s=open(p).read()
old="\tunsigned int lru_counter;\n"
new="\tunsigned int lru_counter;\n\tint head_detached_cache;\n"
assert old in s; open(p,'w').write(s.replace(old,new))
p='src/libgit2/repository.c'; s=open(p).read()
old="\texists = git_odb_exists(odb, git_reference_target(ref));\n\n\tgit_reference_free(ref);\n\treturn exists;"
new=("\texists = git_odb_exists(odb, git_reference_target(ref));\n\n"
     "\tint *detached = &repo->head_detached_cache;\n\t*detached = exists;\n\n"
     "\tgit_reference_free(ref);\n\treturn exists;")
assert s.count(old) == 1; open(p,'w').write(s.replace(old,new))
PY
p4 shelve -c $C >/dev/null && p4 revert -c $C //... >/dev/null
echo "shelved: $A $B $C"
p4 opened 2>&1 | head -2
p4 describe -s -S $C | head -12
