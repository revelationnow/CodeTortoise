# Change Stories: a Review Told as a Few Stories — Design

Date: 2026-10-04. Status: draft for review. Step 5 of the production-readiness work.

## 1. Why

Step 4 keeps every board at 30 nodes or fewer, but a large review is still hard to take in. On libgit2 #6896 (lab
README, "Large changes") the reader gets 8 clusters named after arbitrary functions and about 240 nodes, every changed
function drawn as the same "Δ MODIFIED +1 −1" box, and boards covered in dashed field lines. Yet 181 of the change's
187 changed lines are one edit: `git_vector_free(` became `git_vector_dispose(` in 65 files. The review never says so.

The graph of code is the wrong top level. A reviewer wants to know what the change does, in a handful of statements,
and where to look first.

Goals (agreed 2026-10-04):
- **Every review opens on a list of at most 15 stories**: what the change does, riskiest first.
- **A repeated edit is one story** with a count ("`git_vector_free` → `git_vector_dispose` at 181 sites in 65 files"),
  shown as a list of sites, not as boxes.
- **A story opens on its steps**: a numbered list saying what each function on the path does. A graph of at most 12
  nodes, each with a note on what changed, is one tab away; today's board is one link away.
- **Fewer nodes, richer nodes.** No hairball by default: field lines only for what is selected; a struct is one node.
- Nothing is lost: every changed function, flow and finding is in exactly one story (a function with a repeated edit
  and other edits is in its behaviour story and listed by the repeated edit's story).

## 2. Stories

The board stage builds the stories after the flows and findings, from the diff map, the change set's before and after
text, the impact model and the flows. Four kinds:

### 2.1 Mechanical: a repeated edit

**Substitutions.** For each changed function (modified or signature changed), the function's before and after text is
diffed line by line (difflib). Within each hunk with as many removed lines as added ones, the lines are paired in order.
A pair is a substitution when, split into C tokens (identifiers, numbers, string and character literals, operators and
punctuation; whitespace and comments ignored), the two lines differ in exactly one run of consecutive tokens. The
substitution is that run's old and new text: `git_vector_free` → `git_vector_dispose`, `-1` → `GIT_EINVALID`,
`int` → `size_t`. A hunk with unequal counts, or a pair differing in two places, is not a substitution.

**The story.** A substitution forms a mechanical story when at least **2** functions are explained by it: every changed
line of the function is a pair with that substitution. Changed lines outside functions (headers, macros, globals) with
the same substitution count as sites of it. A function that also has other edits belongs to its behaviour story,
tagged "also has `<old>` → `<new>`", and the mechanical story lists it under "also in N functions with other edits".
A function explained by two substitutions (each line one or the other) joins the story with more sites.

**Title** (template): "`<old>` → `<new>` at N sites in M files" plus "(K in tests)" when some sites are test code
(`is_test_path`). Sites are line pairs.

**Effects.** A function in a mechanical story can still cause flows (renaming a call changes what is called). All flows
caused by one mechanical story's functions form one behaviour story, "What `<old>` → `<new>` changes" (§2.2), and the
mechanical story's sites with flows are marked "has an effect" with a link to it.

### 2.2 Behaviour: what the change causes

**Seeds.**
1. Each changed function outside mechanical stories that causes at least one flow is a story holding all its flows.
2. Each mechanical story whose functions cause flows gives one story holding those flows (§2.1, "Effects").

**Joining.** Every other changed function that is not in a mechanical story and not test code joins the seed story it
is nearest to, counting hops through changed code joined as clusters join it (calls, and field accesses the change
added or removed; step 4 §2). A tie goes to the riskier story. Functions no seed reaches are grouped by connection
(`cluster_change` on what is left) into "Other changes in `<directory>`" stories, named as clusters are named.

**Findings** belong to the story holding their node (the first node of a finding with several; a finding on a field
goes with the story whose code changed that field's access).

**Title** (template, from the seed's flows): "`<cause>` now writes `<field>`; `<landing>` reads it" for a state flow,
"`<cause>` can now return `<value>`; `<caller>` ignores it" for a contract flow; several landings: "…; read by
`<landing>` and N more". A seed of kind 2 uses "What `<old>` → `<new>` changes: `<landing>` and N more see new
values".

### 2.3 Tests

Changed test code (`is_test_path`) not in a mechanical story forms one "Tests" story: its functions, grouped by file.

### 2.4 The list

- **Summary line** at the top, from counts: "Mostly mechanical: 181 of 187 changed lines are one edit
  (`git_vector_free` → `git_vector_dispose`)" when mechanical sites are at least half the changed lines; otherwise
  "N behaviour stories, M mechanical edits, K test changes".
- **Order:** behaviour stories by risk (highest finding severity, then flow severity: high, medium, low, none; ties by
  more flows, then more changed functions), then "Other changes" by the same rule, then mechanical stories by sites
  (marked "skim"), then Tests.
- **At most 15 entries** (`analysis.max_stories`). Past that, the least risky "Other changes" stories merge by
  directory (nearest shared directory first), then the smallest mechanical stories are folded into one "N more
  repeated edits" story that lists each substitution. Behaviour seeds are never merged: when they alone exceed the
  cap, the seeds past it are listed, collapsed, under "N more behaviour stories" at the end of the behaviour section.
- **Ids** `S1…` in list order.

### 2.5 Labels

An anonymous struct or union is named, everywhere a field label appears (facts, boards, stories, flow text, findings):
by the typedef that names it; else by the enclosing named struct and member (`filesystem_iterator_frame.<member>`);
else `anonymous struct (<workspace-relative path>:<line>)`. A label never contains an absolute path. This applies to
reviews run after the change; stored reviews keep their labels.

## 3. The story page

### 3.1 Behaviour and "Other changes" stories

**Header:** title, risk, one-line summary, counts ("2 flows · 1 finding · 4 functions"), ✦ Explain (AI title and
summary), and "Whole graph ›" (§5).

**Steps tab (opens first).** Each flow is a numbered list of steps, as on today's phone Flows tab, on desktop too:
"entry · src/libgit2", "calls `filesystem_iterator_frame_pop`", "Δ now writes `frame.size`" with the changed lines,
"reads `frame.size` here ⚠" for the landing with its line. Tapping a step opens its code inline (the function's diff
for changed code, the relevant lines otherwise), with comments as today. Several flows: a switcher ("flow 1 of 3").
Below: "Also changed in this story" (its other functions, each with a one-line note and its diff), the story's
findings, and "also has `<old>` → `<new>`" tags linking to the mechanical story. A story without flows opens on that
list.

**Graph tab.** At most 12 nodes (`analysis.story_graph_nodes`), chosen in order: the cause, the selected flow's path
and landing, the other flows' paths, the story's other changed functions, then neighbours while there is room. A
story with more required nodes shows its first flow in full plus a "+N more changed functions" node that opens the
list.
- **Structs:** the fields a story's nodes touch are drawn as one node per struct, listing those fields; selecting a
  field's line highlights it.
- **Rich nodes:** name, a one-line note ("now writes size", "no longer writes contents", "calls `git_vector_dispose`
  instead of `git_vector_free`", "signature changed", "+3 −1"), a risk border (the story's finding severity on its
  nodes), a finding count.
- **Lines:** calls on the selected flow always; other calls and all field reads and writes only for the selected node
  or flow.
- No lens shrinking (12 nodes fit at full size); pan and zoom as today. "+N callers / callees" expands the graph
  (step 4's expansion, Reset included).

### 3.2 Mechanical stories

Summary (substitution, sites, files, tests), then the sites grouped by directory → file → function, each with a
one-line before/after snippet and "has an effect ›" where it applies. A "Hide tests" filter. "Also in N functions with
other edits" links to their stories. No graph tab.

### 3.3 Tests story

Test functions grouped by file with their diffs; each names the changed code it calls, linked to that code's story.

## 4. Data and API

**Blobs.** The board stage writes, besides today's boards:
- `stories`: `{summary, stories: [{id, kind: "behaviour"|"other"|"mechanical"|"tests", title, summary,
  text_source: "template"|"llm", risk, counts: {flows, findings, functions, sites, files, test_sites}, nodes,
  flows, findings, board: cluster id or null}]}`.
- `story:S<n>`: the story's steps (flow ids and per-step notes), its graph (a board of at most 12 nodes with notes and
  struct nodes), its other functions with notes, and for a mechanical story its sites (`{file, function, line, before,
  after, test, effect_story}`).
- Re-runs replace them with the boards, in one transaction (boardstore).

**Endpoints.**
- `GET /api/reviews/{rid}/stories` → the list; 404 "this review has no stories: re-run it" for older reviews.
- `GET /api/reviews/{rid}/stories/{sid}` → one story; `?expand=N12:callers,…` grows its graph (step 4 rules, 50 at
  most); 404 "That story no longer exists after the re-run."
- `GET /api/reviews/{rid}/locate` also returns `story` for a node, flow or finding.
- `POST /api/reviews/{rid}/explain` accepts `kind: "story"`: the AI rewrites that story's title and summary (counted
  against the review's AI budget like other explanations); the result is stored with `text_source: "llm"`.

**AI.** New `llm.upfront_stories: 3`: when a review runs, the up-front pass rewrites the titles and summaries of the
top 3 behaviour stories within the budget. Prompts carry the story's flows, findings and diffs; citations are checked
as today. Flow narratives (`upfront_flows`) are unchanged.

**Configuration.** `analysis.max_stories: 15`, `analysis.story_graph_nodes: 12`, `llm.upfront_stories: 3`.

## 5. Interface

**Routes.**
- `/r/:id` — the story list (summary line, entries with kind, risk, title, summary, counts; mechanical entries
  compact and marked "skim"). A link "Boards ›" opens today's view.
- `/r/:id/s/:sid` — a story (`?tab=graph`, `?node=`), with ‹ › to the previous and next story.
- `/r/:id/board` — today's single board; `/r/:id/overview` — today's overview of a split review; `/r/:id/c/:cid` —
  cluster boards, unchanged. "Whole graph ›" on a story opens the board holding its cause, focused on it.
- A review without stories (run before this step, or whose story building failed) opens `/r/:id` on today's page.

**Citations** (findings, comments, @tortoise): a node, flow or finding opens its story (Steps tab, scrolled to it);
`?node=` on a story that doesn't hold the node opens the story that does.

**Findings page:** grouped by story, with a story filter (replacing the cluster grouping).

**Change panel** (What's this change?) stays on the story list and story pages: the whole change's summary on the
list; the story's files and findings on a story.

**Phone:** the story list is the first screen; a story's bottom tabs are Steps · Graph · Files · Summary; the ☰ menu
lists the stories and "Boards".

## 6. Limits and failures

- Story building runs after the boards; if it raises, the review keeps its boards, the board stage is degraded with
  "stories failed: <error>", and `/r/:id` opens on today's page.
- Very large mechanical stories (thousands of sites) list sites by file with a count, loading a file's sites when it
  is opened.
- Functions whose text is missing on one side (added, removed) are never mechanical.
- Generated or binary files are ignored as today.

## 7. Lab check

On libgit2 #6896 imported as in the lab README: about 4 entries — the rename as one mechanical story of 181 sites in
65 files with its tests counted, "What `git_vector_free` → `git_vector_dispose` changes" (or the changed
`git_vector_free` itself) with its flows, the remaining behaviour, and Tests. No story graph above 12 nodes; no
absolute path in any label. Record the counts for #6896 and two other libgit2-big changelists in the README.

## 8. Testing

- **Substitutions** (synthetic texts): an exact swap; a swap plus another edit in the same function; unequal hunks; a
  pair differing in two places; 2 functions versus 1; header and macro sites; test sites counted; comments and
  whitespace ignored; a function explained by two substitutions.
- **Behaviour grouping** (synthetic impact graphs): one seed per flow-causing function; flows of mechanical functions
  forming one story; joining by nearest hop; ties to the riskier story; "Other changes" by connection; tests; the
  15-entry cap and its merge order; every changed function, flow and finding in exactly one story.
- **Labels:** anonymous struct by typedef, by enclosing member, by relative path; never absolute.
- **Graph:** at most 12 nodes; the "+N more" node; struct nodes; notes; field lines absent until selection
  (frontend).
- **Small fixture:** the expected stories and titles; old reviews without stories open today's page.
- **API:** list, story, expansion, 404s, locate with stories, explain `story`, unauthenticated refusals.
- **End to end** (desktop and phone): list → story steps → graph → Whole graph and back; a citation opening its
  story; the mechanical story's sites and "Hide tests"; ‹ › between stories.
- **Lab:** §7, by hand.

## 9. Out of scope

- Marking stories as reviewed or tracking reading progress.
- Comment threads on a story itself (comments stay on reviews, layers, functions and lines).
- Detecting repeated edits with different names ("same shape") — only exact substitutions.
- Changing how flows, findings or clusters are computed.
