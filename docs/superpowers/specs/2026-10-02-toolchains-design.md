# Toolchains, Compile Databases and Parse Diagnostics — Design

Date: 2026-10-02. Status: approved; spike done (§5). Step 1b of the production-readiness work (step 1a, the symbol index, is
separate).

## 1. Why

On a production workspace every translation unit failed to load in libclang and fell back to tree-sitter, so the
analysis ran on name matching only. The causes CodeTortoise can't see from the outside, but the code shows several
systematic ones:

- The first word of each compile command is dropped as "the compiler". With a wrapper (`ccache gcc …`) the real
  compiler is then read as a source file.
- `@file` response files are passed through unexpanded, and relative paths inside them break.
- libclang runs in the server's working directory, not the entry's `directory`; only some path flags are made
  absolute.
- The compiler is queried once per language, using the first compile entry, and every file gets that entry's
  include paths and macros. A workspace with several targets parses most files against the wrong headers.
- Only one `compile_commands.json` is read. Files that only appear in a nested database borrow a neighbour's flags.
- The bundled libclang (the `libclang` wheel) stops at 18.1.1, so newer gcc and clang flags are unknown.
- When a parse fails, nothing tells the owner why, short of reading stage messages.

Success: on a workspace with wrapped compilers, response files, out-of-tree and nested builds and more than one
target, files parse with libclang (precise or degraded, not tree-sitter), and when one doesn't, one command shows
why on that machine.

## 2. Compile databases

- `workspace.compile_commands` takes a path (as today), a list of paths or glob patterns, or `auto`.
  `auto` finds every `compile_commands.json` under `workspace.build_root` (default: the folder of the first database
  found by the `init` search: the workspace, then `build*`/`out*` folders beside it), skipping hidden folders.
- All databases merge into one lookup by canonical source path. Each entry remembers its database.
- A file in several databases: with a list, the first listed wins; with `auto`, the deepest database wins (a nested
  build is the specialised build of that component). A file listed more than once in one database: the first entry
  wins. Duplicates with different arguments are counted and reported.
- "Nearest entry" (a file not in any database borrows a neighbour's flags) only looks inside the database whose
  `directory` tree contains the file, never across databases.
- `toolchain.overrides[].compile_commands` pins the database for matching paths.
- The symbol index scope (step 1a) uses the merged file list.

## 3. Reading a compile command

For each entry, in order:

1. **Response files.** Every `@path` argument is replaced by its contents, split with shell rules (GCC style; MSVC
   style for `cl` drivers), recursively, resolved against the entry's `directory`. A missing response file is kept,
   and reported.
2. **Wrappers.** Leading `ccache`, `sccache`, `distcc`, `icecc`, `buildcache` (by base name, with or without a path or
   `.exe`) are skipped, and so is an `env VAR=x …` prefix. The next word is the compiler.
3. **Driver mode.** A compiler whose base name is `cl`, `cl.exe` or `clang-cl` gets `--driver-mode=cl`; MSVC output
   and PDB flags (`/Fo`, `/Fd`, `/Fe`, `/FS`, `/Zi`-family output paths) are dropped like `-o`.
4. **Working directory.** libclang gets `-working-directory <directory>`, so every relative path resolves as it did
   in the build. Path flags are still made absolute and canonical (needed to match unsaved files).
5. **Target.** In order: `--target`/`-target` already in the command; `toolchain.overrides[].target`;
   `toolchain.target`; the compiler's name prefix (`arm-none-eabi-gcc` → `arm-none-eabi`); the compiler's
   `-dumpmachine` (cached per compiler). The host target needs no flag.
6. Output, dependency and colour flags are dropped as today; learned unknown flags are stripped as today.

## 4. Toolchain groups

- A **toolchain key** is: compiler path, target, and the target-affecting flags of the entry (`-m*` arch/ABI/FPU
  flags, `--sysroot`, `-isysroot`, `-std` family is not included). Files with the same key share one driver query.
- The driver query (built-in include paths, predefined macros, resource directory) runs once per key and per
  language, and is cached for the process. The compiler is the entry's own compiler; `toolchain.clang` becomes an
  override for all entries, and `toolchain.overrides[].clang` for matching paths. When neither is set and the entry's
  compiler can't be run, the group parses without built-ins and is reported.
- Each translation unit gets its own group's `-isystem` paths, macro prelude and target.

## 5. libclang

- **Bindings.** Move from the `libclang` wheel (bindings + library, stops at 18.1.1) to the `clang` bindings package
  (21.1.x). The two install the same `clang` module, so only one can be a dependency.
- **Library, in order:** `toolchain.overrides[].libclang` for matching paths; `toolchain.libclang`; a `libclang.so*`
  next to the group's compiler (`<bin>/../lib`, `<bin>/../lib64`) when that compiler is a clang; under each
  `toolchain.search_paths` entry; one fetched by `codetortoise fetch-libclang`; a system LLVM
  (`/usr/lib/llvm-*/lib`, newest first). Among several candidates in one place, the newest version wins.
- **`codetortoise fetch-libclang [--version 23.1.2] [--from <tarball>]`** downloads the official LLVM release for the
  host (Linux x64 or ARM64), verifies it against the release's published checksum, and keeps only `libclang.so*` and
  `lib/clang/<ver>/include` under `<data_dir>/libclang/<ver>/`. `--from` installs from a tarball copied onto an
  offline machine. The resource directory of the library in use is passed to each parse.
- **One library per process.** Parsing already runs in worker processes; each worker loads the library its group
  needs, so a group that needs a vendor fork can use it while the rest use upstream. A group's requests go to
  workers started for that library.
- **Spike results (2026-10-02).** On the bundled fixtures, `clang` 21.1.7 bindings gave facts identical to today's
  (libclang 18) with both the system libclang 21.1.8 and the LLVM 23.1.2 release, once two private binding calls
  (`_CXString.from_result`, used for the version string and binary-operator spelling) were replaced by direct C calls.
  On a heavy C++20 file, bindings 21 with libclang 23 raised on 469 of 175,415 nodes (type kind 182, unknown to the
  bindings); with libclang 21 none did. libclang 23 also needed `-resource-dir` to find `stddef.h`.
- **Therefore:** the bindings and the fetched library share a major version: `clang==21.1.*` and LLVM 21.1.8 by
  default, bumped together when newer bindings are published. Unknown cursor and type kinds are read as "other"
  instead of raising, for vendor or system libraries newer than the bindings. Every parse with a non-bundled library
  passes that library's resource directory. Private binding APIs are not used.
- **Fetch details:** the release tarball is about 1.9 GB (LLVM 21.1.8, Linux x64); `fetch-libclang` streams it,
  keeping only `lib/libclang.so*` and `lib/clang/<ver>/include` (about 230 MB), and checks its SHA-256 against the
  digest GitHub publishes for the asset (25 s on the test machine). `--from` checks against digests pinned in the
  code for the default version, or a `--sha256` given on the command line.

## 6. Configuration

```yaml
workspace:
  compile_commands: auto            # or a path, or a list of paths/globs
  build_root: /work/main/build      # with auto
toolchain:
  clang: /opt/vendor/bin/clang      # optional override; default: each entry's own compiler
  target: armv7m-none-eabi          # optional override; default: from the command or the compiler
  libclang: /opt/vendor/lib/libclang.so   # optional
  search_paths: [/opt/tools, /opt/vendor] # where to look for a libclang
  overrides:
    - match: "dsp/**"               # glob on the workspace-relative source path
      compile_commands: build/dsp/compile_commands.json
      clang: /opt/hexagon/bin/hexagon-clang
      target: hexagon
      libclang: /opt/hexagon/lib/libclang.so
```

Every new setting is optional; a config that works today keeps working.

## 7. Diagnostics

- **`codetortoise check-parse --config tortoise.yaml <file>`** prints: the database and entry used (and others
  ignored), wrappers and response files expanded, the toolchain group (compiler, target, driver query result), the
  libclang path and version and why it was chosen, the exact arguments, stripped flags, the first 20 errors, and the
  result (precise, degraded, or tree-sitter fallback and why). Exit code 0 when libclang loaded the file.
- **Health page:** one warning-level check per toolchain group parses one sample file and shows the first error;
  a list of databases (file counts, duplicates with different arguments) and of groups (compiler, target, libclang,
  file count).
- **`facts` stage message:** the share of files parsed precise / degraded / tree-sitter, and the most common failure
  reason with its count.

## 8. Testing

- Unit: response files (nested, relative, missing), wrappers (each name, with path, `env` prefix), `cl` mode, target
  resolution order, toolchain keys, database merge and precedence (list order, `auto` depth, duplicates, nearest entry
  confined to its database), libclang discovery order.
- Real libclang: one fixture per failure mode (wrapper, response file, relative paths with `-working-directory`,
  `--target=arm-none-eabi` with a fake sysroot, two targets in one workspace getting different macros), each failing
  before the change and loading after it.
- `check-parse` output on those fixtures; Health groups; stage message counts.
- The existing suites stay green on both the old (`libclang` 18) and new (`clang` 21 + fetched 23) libraries during
  the transition.

## 9. Out of scope

- Compilers that are neither GCC- nor clang-compatible (IAR, TI `cl6x`, Green Hills, Tasking): a flag translator is a
  later step if needed.
- Windows hosts.
- Parse result caching and stage performance (step 5).
