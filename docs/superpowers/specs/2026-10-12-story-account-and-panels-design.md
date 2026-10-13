# Story accounts, side-panel findings, collapsible panels — design

Owner feedback 2026-10-12, approved in conversation the same day:

1. The story page says too little: two or three lines. The weak model should take what the strong model produced and
   the story's facts and write a longer, cohesive account that walks through the flows.
2. On the story page, an opened diff or a finding's details is cramped or leaves the page: the vertical panels should
   collapse to give the diff room, a check's Details should open the finding in place, and there should be a way to
   the full list of findings. The CLs page should expand each CL's files and open their diffs without leaving it.
3. Stray endpoints: one API route has no caller left.

## 1. Story accounts

### 1.1 What the reader gets

"What it does" on a behaviour story's page shows the story's **account** in place of its one-to-three-line text:

1. **Purpose**: what the story is for and why, one paragraph.
2. **One section per flow**, in the story's reading order: the entry point, the changed code it reaches, and the
   effect, one paragraph each, headed by the flow's own label (`main → logger_flush → uart_send`).
3. **What it means for the rest of the code**: who else sees the effect, and what to watch.

Every section carries the AI label (`ai-label`). Names in the text are clickable as elsewhere (`NameText`). The story's
place in its thread (`place_text`) follows the account, as it follows the short text today.

Mechanical, test and unsorted stories keep their short rule text. A behaviour story without an account (no LLM
configured, the call failed, or every section was dropped) shows exactly what it shows today.

### 1.2 Inputs

One weak-model call per behaviour story (`svc.llm`, the `llm` config). The prompt holds, within `llm.max_context_tokens`
per call (`storyboard.budget`, most important first):

- the story's title, kind and current short text (`purpose` or `summary`);
- what the strong model said of it, when tier 1 grouped it: `purpose`, each placement's reason (`placements`), `check`,
  `questions`;
- each flow of the story: id, label and what it does (`Flow.text`, `Flow.what`);
- its call paths, before → after contracts and where (`StoryReading.paths`, `.contracts`, `.where`);
- its findings, as `storyboard._finding_text` gives them (shared-sink findings left out, as in the summary job);
- the graph facts of its nodes (`_facts_for_nodes`) and the code snippets of its changed functions (`ctx.snippets`).

### 1.3 Output and checks

The model answers JSON: `sections: [{kind: "purpose" | "flow" | "effects", flow: str | null, text: str, cites: [str]}]`.

A section is kept only when:

- its text is non-empty and keeps the house style for the `explanation` mode (`check_style`, as the story job does);
- it cites at least one node id of the story (its `nodes` or a node on one of its flows) or one of its finding ids;
- a `flow` section names a flow of the story (`flow` is that flow's id); the section's heading is that flow's label.

At most one `purpose` and one `effects` section are kept, the first of each; flow sections keep the story's flow
order, and a second section for the same flow is dropped. When no section survives, the story has no account. Dropped
sections count toward the stage's `style_dropped` note as other AI output does.

### 1.4 When it runs, and storage

The **reading** stage writes the accounts, after `build_reading` (call paths and contracts are known then) and after
the thread text and introduction:

- every behaviour story that is not collapsed gets one call; calls run in parallel up to `llm.concurrency`;
- each call goes through the ledger as the pipeline, as every up-front stage's calls do (purpose `story_account`,
  target the story id), so the review's AI budget and the request log apply; a refused or failed call leaves that
  story without an account and adds a stage note ("N story account(s) not written: …");
- the answers are cached per review in the blob `story_account`, keyed by
  `sha256(ACCOUNT_VERSION | weak model | inputs)` per story, where the inputs are the prompt's facts less what a model
  rewrites earlier in each run (the story's and its flows' retold text, the findings' verdict severities); an
  unchanged story on a re-run reuses its account, a
  forced re-run (`fresh`) rewrites every account. `ACCOUNT_VERSION = 1` lives beside the prompt and is bumped with
  every change to it.

The account is stored on the story's reading (`story_reading:{sid}`), so the story page needs no new request:

```python
class AccountPart(BaseModel):
    kind: Literal["purpose", "flow", "effects"]
    heading: str                 # "What it is for", the flow's label, "What it means for the rest"
    text: str
    cites: list[str] = Field(default_factory=list)

class StoryReading(BaseModel):
    ...
    account: list[AccountPart] = Field(default_factory=list)
    account_files: Files = None  # provenance: the files whose code was in its prompt (ctx.prompt_files)
```

Without an LLM configured the stage writes no accounts and adds no note about them.

## 2. Side panel: findings and tabs

### 2.1 A finding in the panel

The detail panel (`Detail.tsx`) opens a third kind of item besides a node's code and a file's diff:

```ts
export type Open = { node: string } | { file: string; line: number | null; all?: true } | { finding: string } | null;
```

`?open=` spells it `finding:F4` (the existing `readOpen` / `href` pair learns it). The panel shows what the finding page
shows: severity and title, its place (story, CLs, functions), AI analysis, evidence, comments, and acknowledge /
dismiss for the owner. That body moves out of `FindingPage.tsx` into a `FindingBody` component that both use; the
page keeps its crumbs, its previous/next and its own heading.

A check row's **Details** opens `{finding}` in the panel instead of navigating to `/f/{id}?details=1`. The finding page
and its address stay for links from elsewhere (and the previous/next walk). The panel's header for a finding links to
"Open as a page" (`/f/{id}?details=1`) and **All findings** (§4).

### 2.2 Tabs

The panel keeps a tab for every item opened during this visit to the review, most recent last, at most 8 (opening a
ninth drops the oldest that is not active). The tab bar sits in the panel's header: a tab names its item (`F4`, the
file's name, the function's name), the active one is marked, × closes one. Closing the active tab activates its left
neighbour; closing the last closes the panel. The address holds only the active item, so Back and Forward move between
what was open, and a shared link opens one tab. Tabs live in the workspace's state (not storage); a reload starts with
the address's item alone. On a phone the panel stays a full-screen sheet with no tab bar.

## 3. Collapsing panels (desktop)

- The rail and the To check column (the right column of `CheckColumns`, on the overview and on a story) each get a
  collapse button in their header. Collapsed, each is a 28px strip with an expand button and its name written
  vertically ("Contents", "To check" with its open count). Each one's state is remembered per browser
  (`ct.ws.railFolded`, `ct.ws.checkFolded`, read and written in try/catch).
- The side panel's header gets **Focus**: it folds the rail and the To check column and widens the panel to the room
  that frees (the centre keeps at least 360px). Pressing Focus again restores the folds and the panel's width as they
  were before. Closing the panel while focused restores them too. Focus is not remembered across reloads.
- Tablet and phone layouts keep their drawer and sheet; the buttons are not shown there.

## 4. Findings index

A **Findings** tab in the Index (`/i/findings`, after Checks): every finding of the review, info ones included.

- Each row: severity pill, id, title (`tidy`), status (open / acknowledged / dismissed), its story's handle, file and
  line, and a "shared field" mark for a shared-sink finding.
- Sorted by severity (high → info), then id. Two filters above the list: severity (all, or one) and status (all, open,
  acknowledged, dismissed); the filters live in the address (`?sev=`, `?status=`) so a link keeps them.
- A row opens the finding in the side panel (§2).
- The tab's count is the number of findings; the rail's Index lists the new tab.

The To check tile's header (on the overview and on a story) and the finding panel's header link to it ("All findings").

## 5. CLs page

Index › CLs: each CL row gets a ▸ button that expands its files under it, in place: path, action, +/−, as the CL's own
page lists them. A file opens its diff in the side panel (the same `ws.opened({file})` the CL page uses), so the list
stays. An **Expand all** / **Collapse all** button sits above the list. Which CLs are expanded lives in the workspace's
state for the visit. The CL heading still opens the CL's page.

## 6. The stray endpoint

`PUT /api/layers/{level}` (layer rename) has had no caller since its UI went. It is removed with `api.renameLayer`,
`LayerNameIn`, and the code applying the `layer_overrides` key to layer names in the overview, the board and
`services.py`. Names stored through it stop applying; layers show their generated names. Every other route keeps a
caller and needs a login (owner-only where it changes shared state).

## 7. Errors and limits

- An account call that times out, is refused by the budget or answers invalid JSON leaves that story's short text; the
  stage stays ok when at least one account was written, degraded ("N story account(s) not written: <first error>")
  when a call failed and no story got an account.
- A finding id in `?open=finding:` that the review lacks shows "Not found" in the panel, as a missing node does.
- Long names in the new views follow the long-text rules (one-line labels end in an ellipsis with the whole text on
  hover; sentences wrap).

## 8. Testing

- **Backend** (fake LLM client, as the storyboard tests use):
  - an account with purpose, two flow sections and effects is stored on the story's reading, in flow order;
  - a section citing nothing of the story, a flow section naming another story's flow, and a second purpose are
    dropped; with none left there is no account;
  - the cache: an unchanged story is not asked again; `fresh` asks again; the prompt holds the strong model's purpose,
    placements, check and questions when tier 1 grouped the story;
  - no LLM: no account, no note;
  - `PUT /api/layers/1` is 404/405.
- **Unit** (vitest): `readOpen`/`href` round-trip `finding:F4`; the tab list (add, cap of 8, close active); the findings
  filter and sort.
- **e2e** (fake LLM endpoint serving fixed accounts, as the AI specs do):
  - a story page shows the account's sections with the AI label;
  - a check's Details opens the finding in the panel, the story stays, Back closes it; tabs switch between a finding
    and a diff;
  - folding the rail and To check, Focus and restore;
  - the Findings index filters by severity and status and opens a finding in the panel;
  - Index › CLs expands a CL and opens a file's diff in the panel without leaving the page;
  - the long-text check visits `/i/findings` and a story with an account.
