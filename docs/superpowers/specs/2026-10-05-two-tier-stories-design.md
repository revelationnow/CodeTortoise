# Two-Tier Stories: a Strong Model Forms the Stories and Reviews Their Risks — Design

Date: 2026-10-05. Status: draft for review. Follows change stories (2026-10-04-change-stories-design.md) and the AI
budget (2026-10-03-ai-budget-design.md).

## 1. Why

Stories are formed today by fixed rules (`stories.py`); the AI only rewrites a story's title and summary. On real
changes the rules put code in the wrong story:

- **Flows are the only seeds.** A behaviour story starts only from a function that causes a flow (a risky contract or
  side-effect path). A large feature with no risky flow of its own never gets a story; its code joins someone else's.
- **Joins have no reach limit.** The rest of the changed code joins the nearest seed over any chain of call or field
  links, so a whole feature (new functions plus the existing functions edited to call them) is pulled into an
  unrelated risk story.
- **Targets and CLs are ignored.** Code built for a different target in the same codebase, or from another CL, joins
  freely. In lab review 19 (reftable CL 11, programdata CL 12) the clar helper `cl_sandbox_set_search_path_defaults`
  (CL 12, no link to any reftable function) sits in the reftable story S2, merged only because both live under
  `deps/` (the small-cluster directory merge in `clusters.py` step 3).
- **Findings without functions go to the first story.** Header findings (`config.h`, `sysdir.h`: programdata) fall
  back to `drafts[0]` and land in S1, the reftable stack story.

Fixed rules cannot be made precise across every codebase, and the weak local models that answer readers' questions
cannot form stories reliably either. This design splits the AI work in two:

- **Tier 1, a strong model, once per review**: forms the stories from a prepared view of the change and reviews each
  story's risks (side effects, signature changes, return values, changed behaviour, headers).
- **Tier 2, the weak model, on demand**: explains, Ask…, @tortoise, story text, starting from tier 1's work.

Goals (agreed 2026-10-05):
- **Each story has one purpose** a reviewer can check in one sitting: a feature, a fix, a refactor, a bring-up.
- **Code for a different target is a different story**, unless it is genuinely shared code.
- **No large unrelated chunk rides along** with a story.
- **Every story says why its parts are together**, and every finding's verdict cites the code it relied on.
- **Stable from run to run**: the same change gives the same story structure.
- **Prep does the heavy lifting**: the fixed rules hand both tiers facts, so the models check and decide instead of
  hunting.
- **Tier 1 is optional and configurable**: any OpenAI-compatible endpoint, hosted or local. Without it, the rules form
  the stories (better rules than today's, §6).

## 2. Overview

New and changed pipeline stages, in order:

```
… impact → detectors → pieces → stories → board → review → verdicts → llm → finalize
```

- **pieces** (rules, §3): target of every changed file; the change cut into conservative pieces; typed links between
  pieces; an evidence card per piece; prepared facts per finding (§5.1).
- **stories** (tier 1, §4; rules fallback §6): the strong model groups pieces into stories with reasons; code checks
  every placement.
- **board**: unchanged, except that a story's board and graph are built from its pieces' nodes.
- **review** (tier 1, §5): one pass per story answers fixed questions about each of its findings.
- **verdicts** (tier 2, today's stage): only for side-effect findings tier 1 did not judge.
- **llm** (tier 2, today's stage): story text only for stories tier 1 did not name; flows, findings, summary as today.

The validated tier-1 output is stored as the review's **brief** (§7.2): stories, per-story notes, per-piece reasons,
per-finding verdicts and a short change overview. Tier 2 reads the relevant part of the brief at the top of every
prompt (§8).

## 3. Pieces (rules, no AI)

### 3.1 Targets

Each changed file gets a set of targets, resolved in order (first that applies):

1. **Configured names**: `targets:` in config, a list of `{match: <glob on the workspace-relative path>, name: <str>}`;
   the first match wins.
2. **Compile database**: the database the file's command came from, named after its directory relative to
   `build_root` (`build-modem/compile_commands.json` → `build-modem`). A file with commands in several databases gets
   all of their names.
3. **Compiler triple**: the toolchain group's target (`arm-none-eabi`, `hexagon`), when the file has one database.

A file with more than one target is **shared**. A file with no command (a header, a file outside every database) takes
the union of the targets of the translation units that include it (the index's include graph); with none, it takes
the target `unknown`. A review with one target shows no target chips anywhere.

### 3.2 Cutting the change into pieces

A piece is a small set of changed nodes that is almost never wrong to keep together. Separating code too much is
harmless (tier 1 joins pieces); joining too much is what this stage avoids. Pieces never span two targets (a shared
file's code is one piece marked shared) and never span two CLs. Cut in this order; each changed node goes in the first
piece that takes it:

1. **Tests**: changed test code (`is_test_path`), one piece per target and directory.
2. **Repeated edits**: one substitution explaining at least 2 functions (change stories §2.1), one piece per
   substitution and target.
3. **New code**: each connected group of added functions (call or shared-field links among them), together with the
   changed existing functions that directly call into the group, within one target and CL.
4. **Connected edits**: the remaining changed functions joined by a direct call or a shared changed field, within one
   target, one CL and one directory. No piece is wider than 2 hops between any two of its nodes; a longer chain is cut
   at its weakest link (fewest calls), ties at the lowest node id.
5. **Declarations**: each changed header (its macro, type and declaration changes from the diff map) is one piece.
6. **Singles**: anything left is a piece of one node.

Pieces are numbered `P1…` in a fixed order: by target name, then CL, then the first file's path, then the first
node's line. The same change always gives the same pieces with the same ids.

### 3.3 Links between pieces

A link joins two pieces with a type and a count: `call` (changed code in one calls code in the other), `field` (both
change access to a field), `sub` (same substitution), `uses` (a declaration piece's header is included by, and its
changed names are used in, the other piece), `name` (the pieces' functions share a name prefix of at least 2 tokens,
`reftable_stack_…`). The count is the number of edges. A link's strength is its count; no other weighting.

### 3.4 Evidence cards

One card per piece, at most 300 tokens, always in the same field order:

```
P7  new code · target modem · CL 412 "modem: add LTE band 71 support"
files: modem/rf/band71.c (+212 new), modem/rf/bands.c (+9 −2)
functions: band71_init (new): sets up the band-71 RF tables …; bands_select (modified): adds a case for band 71 …
flows: — · findings: F12 (contract, bands_select: new return value)
links: → P3 call ×3 · → P9 name ×2
```

Function notes come from the change stories note builder (`_note`), one line each, at most 5 functions (most changed
lines first) with "+N more". Cards are produced by code only.

### 3.5 Change overview

Sent before the cards, at most 1500 tokens: each CL with its full description (truncated at 600 tokens), and per target
the changed files' count, new and modified lines and a directory map (directories with changed files and their line
counts, depth-limited to fit). Shared files are listed once with their targets.

## 4. Tier 1: forming the stories

### 4.1 Input

One prompt per **chunk** (§4.5): the rules (§4.2), the change overview, the chunk's piece cards, the link table among
them, the flows and findings tied to its pieces (one line each). No proposed grouping is sent: the model forms the
stories itself.

**Tools** (the same round-based loop as @tortoise; one AI call however many rounds; `llm.strong.rounds`, default 20):
- `piece_code(P)`: the piece's changed functions, before and after, with 3 lines of context.
- `diff(file)`: the file's diff in this change.
- `neighbours(fn)`: callers and callees of a function, with whether each changed.
- `cl(n)`: a CL's full description and file list.

### 4.2 The rules

A fixed text block, versioned by `STORY_RULES_VERSION` (an integer in `llm/stories.py`, bumped with every wording
change), written as a procedure the model follows in order:

1. Split the pieces by target. Different targets are different stories. A shared piece goes with the story that uses
   it most (most links); other targets' stories that touch it name it under "related".
2. Within each target, find the purposes: what each CL description says it does, and what each new-code piece adds.
3. Place every piece in the purpose it serves. New code goes with the edits that call it. A declaration piece goes
   with the story that uses its changes most.
4. Join pieces from different CLs only when a link joins them, or when both CL descriptions state the same purpose
   (quote both, exactly as written).
5. A story with more than 12 pieces or 40 changed functions must be split along its weakest links into purposes.
6. Give each story a title (at most 10 words: what changed and who is affected), a purpose (one sentence), what a
   reviewer should check (at most 3 points), open questions (at most 3), and related stories by id.
7. Never place a piece twice. A piece you cannot place goes to "unsorted" with a reason.

### 4.3 Output

```json
{"stories": [{"key": "a", "title": "…", "purpose": "…", "check": ["…"], "questions": ["…"], "related": ["b"],
              "pieces": [{"id": "P7", "reason": "same_feature", "evidence": ["P3", "CL412"],
                          "quote": ["add LTE band 71", "band 71 tables"]}]}],
 "unsorted": [{"id": "P9", "reason": "…"}]}
```

Reason codes (enum): `starts_purpose` (the piece that defines the story), `same_feature`, `caller_of_new_code`,
`same_fix`, `same_refactor`, `shared_code`, `declaration_used`, `split_too_big`. `quote` is required only for a
cross-CL join without a link.

### 4.4 Checks

Code checks every placement on its own; a failed placement moves that piece to the **Unsorted** story with the
failure as its reason, and the rest of the answer stands:

- Piece and evidence ids exist; every piece is placed exactly once (a second placement is dropped).
- A story holds pieces of one target, except a `shared_code` placement of a shared piece.
- A piece from a different CL than the story's first piece needs a `call`, `field`, `sub` or `uses` link to a piece
  already in the story, or two `quote` strings each found verbatim in one of the two CLs' descriptions.
- Title, purpose and notes keep the house style (`_titled`, `_styled`); a failing title falls back to the rules'
  title for that story, the placements stand.

The stage message reports stories formed, pieces placed and pieces unsorted.

### 4.5 Large changes

A chunk is one target's pieces. When a chunk's prompt would exceed 60% of `llm.strong.context_tokens`, it is split by
CL, then by top directory. After the chunks, one **merge pass** sees only each story's title, purpose, targets, CLs
and piece ids (not the cards) and may: name related stories across chunks, and merge two stories of the same target
that it shows serve the same purpose (checked as in §4.4). A change whose cards fit in one prompt has no merge pass.

### 4.6 Stability

- **Fixed input**: pieces, ids, cards and order are deterministic (§3); the rules text is versioned.
- **Temperature 0** when `llm.strong.temperature` is set (default 0; `null` for endpoints that reject it).
- **Cache**: the brief is stored under a hash of (cards, link table, overview, rules version, model name). A re-run of
  an unchanged change reuses it; the owner's **Re-run stories (fresh)** bypasses the cache.
- **Agreement mode** (`llm.strong.agree: 2`): two runs; two pieces are in one story when both runs put them together;
  a piece the runs disagree on is decided by a third run's placement. Titles and notes come from the first run. Costs
  2–3 calls per chunk.
- **Measuring**: `codetortoise stories-check <review> --runs N` runs the stories stage N times without caching and
  prints, for each pair of pieces, how often they shared a story, and an overall agreement score (the share of piece
  pairs every run agreed on). It changes nothing stored.

## 5. Tier 1: reviewing each story's risks

### 5.1 Prepared facts

For each finding, code prepares facts before any model sees it:

| Finding kind | Facts |
|---|---|
| Signature changed | Every call site of the function, each marked: updated in this change · not updated · compiled only in another target · not in any compile database |
| New return value | Every caller and its handling of the result: ignored · compared (with the values compared against) · propagated · stored, with the line |
| Field write / side effect | Every reader and writer of the field; which of them changed; each reader's lines that use it |
| Body changed, same contract | Callers and the lines that use the function's result or effects |
| Header change | Each changed macro, type or declaration, and the files that use it, with lines |

### 5.2 The pass

One call per story (the tools of §4.1 available), given the story's brief, its pieces' cards, and for each finding its
facts and fixed questions:

- Signature: do the updated sites match the new signature; is any site left behind?
- Return value: does any caller mishandle the new value?
- Field / side effect: does any reader's assumption break; is this a hazard or a normal side effect?
- Behaviour: does any caller rely on the old behaviour; should a reviewer confirm it?
- Header: do all users still compile and mean the same thing?

Each answer is `hazard` (a clear problem, with the reason), `needs_review` (behaviour changed; a person should
confirm) or `no_hazard` (with the reason), and cites node ids or file:line it was shown. An answer citing nothing it
was shown is rejected and the finding stays as the detectors left it.

### 5.3 Effect

- Severity: `hazard` → high, `needs_review` → medium, `no_hazard` → info. Findings are renumbered by severity, as the
  side-effect verdicts do today; boards recolour (`boardstore.recolor`).
- A story's risk is the highest severity among its findings after the pass.
- The finding records `verdict`, `verdict_reason`, `verdict_cites` and `verdict_source: "tier1"`.
- When tier 1 runs, the tier-2 `verdicts` stage judges only side-effect findings tier 1 did not answer.

## 6. Without tier 1: the rules' stories

When `llm.strong` is absent, unreachable, out of budget, or a chunk fails, its pieces are grouped by rules:

- Pieces join when a `call` link with count ≥ 2 or a `field` link joins them, within one target and one CL.
- A group containing a flow's cause is a behaviour story, riskiest first; the rest are "Other changes" named by
  directory; repeated edits and tests as today.
- A declaration piece joins the group that uses its changes most (`uses` count); none: its own story.
- A finding without nodes goes to the story of the piece its file belongs to; none: no story (it stays in the rail's
  Findings list and on the Whole change page).
- No directory-only merges across targets or CLs. Over `max_stories`, "Other changes" merge only within a target and
  CL, by directory, then the list collapses as today.

The stage reads **Degraded** with the reason when it fell back for any chunk.

## 7. Data

### 7.1 Models

- `Piece`: id, kind (`tests`, `repeated`, `new`, `edits`, `declarations`, `single`), targets, shared, cl, nodes,
  files, card text.
- `PieceLink`: a, b, type, count.
- `Story` gains: `targets: list[str]`, `pieces: list[str]`, `placements: list[{piece, reason, evidence, quote}]`,
  `purpose`, `check: list[str]`, `questions: list[str]`, `related: list[str]`, `source: "tier1" | "rules"`, and a new
  kind `unsorted`.
- `Finding` gains: verdict value `needs_review`, `verdict_cites: list[str]`, `verdict_source: "tier1" | "tier2"`.

### 7.2 The brief

Stored per review (table `briefs`: review id, cache key, JSON, created at): the change overview, pieces, links, the
stories with their notes and placements, and per-finding verdicts. Re-runs with an unchanged cache key copy it.
Reviews stored before this design keep their stories; a re-run builds new ones.

## 8. Tier 2 with the brief

Every tier-2 prompt about a review starts with the relevant part of the brief, within 800 tokens:
- explain / Ask… on a finding: its story's title and purpose, its verdict, reason and prepared facts;
- on a story, flow or file: the story's purpose, what to check, open questions;
- @tortoise: the change overview and the story of the anchor, if any.

Tier 2 answers questions and digs deeper; it never regroups stories or changes a tier-1 verdict. A disagreement is
its answer in the finding's thread. The story-text job skips stories with `source: "tier1"`.

## 9. Config, budget and health

```yaml
llm:
  strong:                    # optional; absent = rules only
    base_url: https://…      # any OpenAI-compatible endpoint
    model: …
    key_env: TORTOISE_STRONG_KEY
    context_tokens: 64000
    temperature: 0           # null when the endpoint rejects it
    rounds: 20
    agree: 1
  budget:
    tier1_per_review: 40     # tier-1 calls per review (stories, merge, risk passes)
targets:
  - { match: "modem/**", name: modem }
```

- Tier-1 calls are recorded in the ledger with purposes `stories`, `stories_merge`, `review`; they count against
  `tier1_per_review`, not the tier-2 budgets. The AI usage panel shows tier 1 and tier 2 separately.
- Health checks the tier-1 endpoint like the tier-2 one. When its host is not localhost or a private address, Health
  says so plainly: "code from reviewed changes is sent to <host>".
- Past the tier-1 budget: remaining chunks use the rules (§6); remaining stories' findings go to tier-2 verdicts, then
  stay neutral.

## 10. UI

- **Story page**: target chips beside the CL chips; **Why these belong together** (each piece: its files, reason in
  words, evidence links); **What to check**; **Open questions**; **Related** ("see S4 · modem").
- **Unsorted** story: listed last, marked "needs a person to place these", each piece with the check that failed.
- **Finding page**: the verdict line shows "AI review" with hazard (red) / needs review (amber) / no hazard, the
  reason, and its citations as links.
- **Rail**: a target chip on each story row when the review spans more than one target.
- **Owner**: **Re-run stories (fresh)** beside Re-run.

## 11. Testing

- **Unit**: target resolution (configured glob, compile database, triple, shared file, header via includers,
  unknown); piece cutting on small fixtures (two targets sharing a file; a new feature with its callers; a 4-hop chain
  cut at 2; a header-only change; a repeated edit; tests); link counts; card order and stability; prepared facts per
  finding kind; placement checks (unknown id, duplicate, cross-target, cross-CL without link or with an invented
  quote → Unsorted); chunking at 60% of context; cache key; agreement mode; the rules fallback (§6), including header
  findings placed by file and no cross-CL directory merge.
- **fake_llm**: tier-1 replies for stories, merge and risk passes, good and malformed, keyed by prompt markers.
- **Pipeline**: tier 1 absent → rules stories, stage Degraded only when configured but failing; tier 1 present →
  stories from its answer; budget exhausted mid-way → mixed, reported.
- **e2e**: story page shows targets, why-together, what to check, related; Unsorted shown; finding verdict colours and
  citations; Health's "code is sent to" notice.
- **Lab**: review 19 rebuilt: the clar helper is in the programdata story; F2 (`config.h`) and F4 (`sysdir.h`) are in
  the programdata story; no story mixes CL 11 and CL 12 without a link. `stories-check 19 --runs 3` with the configured
  strong model reports its agreement.

## 12. Out of scope

- Readers moving pieces between stories by hand.
- Tier 1 writing flow or finding prose (tier 2 keeps that).
- Per-target boards: boards stay as they are; only stories split by target.
