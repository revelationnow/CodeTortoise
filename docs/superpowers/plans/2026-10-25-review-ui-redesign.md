# Flow Groups, Thread Sections, Quieter AI Marks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer owner feedback 2026-10-24: AI-written text keeps showing but loses its `AI` chips (a faint violet edge and a hover instead), headings become dark sentence-case titles, the header shrinks to one quiet row with a ⋯ menu, the overview becomes one section per thread with lined-up counts, the outline becomes an accordion with pinned thread bars, and a story's Flows tab groups its flows by what changed into one-line rows that open in place, tick and step with J/K/F.

**Architecture:** Pure rules live in small tested modules (`lib/aiMarks.ts`, `workspace/reviewMenu.ts`, `reading/overview.ts`, `workspace/outline.ts`, `reading/flowGroups.ts`); components consume them: `AiText`/`AiName` replace every chip, `ReviewMenu` takes what leaves the header, `Overview`, `Outline` and a new `FlowsTab` are rebuilt on the same data. The backend changes in one place: a check row sends `related` (the changed function that raised it, already computed as `cause_fn`), which ties a flow to its places.

**Tech Stack:** FastAPI / pydantic v2 backend (pytest, ruff); React 19 + react-router 7 + TypeScript (strict, `noUnusedLocals`, `noUnusedParameters`) + Vite 8 (vitest in node for `src/**/*.test.ts`, Playwright 1.63 e2e against the built bundle with fixture servers).

**Spec:** `docs/superpowers/specs/2026-10-25-review-ui-redesign-design.md` (approved 2026-10-25, commit 94ced2d).

**Phases** (one branch, `ux-redesign`; each ends with a green suite and screenshots for the owner): **phase 1** = Tasks 1–6 (spec §1–§4), **phase 2** = Tasks 7–9 (§5–§6), **phase 3** = Tasks 10–14 (§7–§8).

## Global Constraints

- The repo is public: never use the owner's proprietary identifiers in code, tests, docs or commits. Examples use the fixture names (`uart_send`, `logger_flush`, `hal_write`, `Uart::errors`, `stats_b1`…) and the spec's public libgit2 names.
- AI-written text always stays visible; only the labels marking it as AI go (owner, 2026-10-24).
- Colour token, in both theme blocks of `styles.css`: `--ai-edge: #ddd3fb` (light), `--ai-edge: #4f4378` (dark).
- `AiText`: 2px left edge in `--ai-edge`, 10px padding to its left, a `title`, visually hidden `Written by AI. ` first; renders as the element it replaces. `AiName`: the same `title`, visually hidden `Written by AI: `, no edge. Outline rows and navigation lists carry no AI mark.
- Hover text: `Written by AI`, plus ` · <model>` only for a story's title, purpose, suggested checks and questions when `story.source === "tier1"` (`AiView.strong`, when set), and for a file summary (its `by`).
- Heading style: sentence case, `color: var(--ink)`, `font-weight: 650`, no `text-transform`, no `letter-spacing`; 16px for `h2`, 15px for `h3` and `h4`; 20px above, 6px below.
- Wording is exact as the spec gives it (`Review menu`, `Workspace drift · N`, `Stage notes · N`, `AI calls used · X of Y`, `How to read this page`, `Re-run`, `Re-run stories, fresh`, `N checks open`, `Start with Thread A ›`, `Show the other N stories ▸`, `Show fewer ▴`, `All read ✓`, `Show N more`, `Looks fine`, `Reopen`, `Next flow ›`, `Also in this story:`…).
- The AI pill shows only when AI is configured and `used >= 0.9 × budget`.
- Outline thread bars: fixed height 36px; one thread open; the last opened kept per review under `ct.ws.<review id>.thread`. Every storage read and write goes through `board/prefs.ts` `load`/`save` (try/catch inside).
- Overview: the first 4 stories of a thread show; a Flows group shows 8 rows before `Show N more`.
- One-line labels (bars, section names, flow rows, chips) end in an ellipsis with the whole text on hover (`title`); sentences wrap; nothing scrolls sideways at 390px.
- No node id (`N<digits>`) is ever shown: names go through `NameText`/`Ticks`/`plainNames`.
- Commit with `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`; every message ends with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH`. Never push.
- Backend tests: from `backend/`, `env PYTHONPATH=$PWD .venv/bin/python -m pytest -q -p no:cacheprovider tests`; lint `.venv/bin/ruff check codetortoise tests`. Never use `uv`.
- Frontend checks: from `frontend/`, `npx vitest run` and `npx tsc --noEmit`. `npm run build` (= `tsc --noEmit && vite build`) writes the bundle the e2e servers serve: rebuild before every e2e run.
- e2e, from `frontend/` (create `.pwtmp` first, delete it when done; Chromium crashes when `/tmp` is full):
  `mkdir -p $(git rev-parse --show-toplevel)/.pwtmp && TMPDIR=$(git rev-parse --show-toplevel)/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) $(cd ../backend && pwd)/.venv/bin/python -m codetortoise.cli" npx playwright test <specs>`
  Below, `E2E <specs>` stands for that command. Kill stray servers by PID, never `pkill -f`; never touch the lab server or anything on 192.168.1.135.

## Review Focus

1. **A reading stored before `related`** (every review run before this branch): no row may show a tick box, every chip must still appear (falling back to the group holding the first flow in the cause's `flows`), and nothing may throw. Unit test in Task 11; e2e in Task 12 (a route strips `related`).
2. **A review with no threads** (only tests, or nothing changed): the overview says `The change`, shows no column row and no sections, and its start button says `Start here ›`. Unit test in Task 7; e2e in Task 8.
3. **No AI configured**: no `AI calls used` item in ⋯, no `Explain`/`Summarise`/`Ask…` button, no AI pill. Unit test in Task 6 (`menuItems` with `ai: null`, `nearLimit(null)`); e2e in Task 6 (mention.spec "without an AI").
4. **Typing in a text field, or a cause open in the side panel**: J, K, F and Enter on the Flows tab must type letters or stay the stepper's, never move rows or mark places. E2e in Task 13.
5. **Very long thread names and story titles**: thread bars and section headers stay one line with an ellipsis and the whole name on hover; nothing scrolls sideways at 390px. E2e in Task 8 and Task 9 (long-text.spec).

---

## File Structure

Backend:
- `backend/codetortoise/reading.py` — `Check.cause_fn` (excluded from dumps) becomes `Check.related: str | None = None` (sent and stored).
- `backend/codetortoise/causes.py` — reads `.related` instead of `.cause_fn`.
- Tests: `backend/tests/test_reading.py`, `backend/tests/test_web.py`.

Frontend, new:
- `src/lib/aiMarks.ts` (+ test) — the hover text and the model that wrote a story's text.
- `src/components/AiText.tsx` — `AiText` (edge) and `AiName` (inline).
- `src/lib/useMenu.ts` — a popup menu's focus, arrow keys, Escape and outside click (the Explain menu and ⋯).
- `src/workspace/reviewMenu.ts` (+ test) — the ⋯ menu's items and its dot.
- `src/workspace/ReviewMenu.tsx` — ⋯, its menu and its panels.
- `src/workspace/outline.ts` (+ test) — which thread is open, pinned bar offsets, the remembered thread.
- `src/reading/flowGroups.ts` (+ test) — flow groups, their titles and lines, a flow's places, a group's causes, row sentences.
- `src/workspace/Chips.tsx` — the cause chips (moved out of `StoryTabs.tsx`).
- `src/workspace/FlowsTab.tsx` — the Flows tab: groups, rows, ticks, folding, keys.
- `src/workspace/keys.ts` — `typing()`, shared by `CauseStepper` and `FlowsTab`.
- e2e: `e2e/header-menu.spec.ts`, `e2e/thread-sections.spec.ts`, `e2e/flow-groups.spec.ts`.

Frontend, changed:
- `src/styles.css`, `src/workspace/workspace.css` — token, edge, headings, menu, sections, bars, rows; chip styles removed.
- `src/components/Explain.tsx`, `Comments.tsx`, `AiPill.tsx`, `HeadlinePill.tsx`; `src/lib/aiState.ts` (+ test) — `nearLimit`.
- `src/reading/causes.ts` (+ test) — the progress line says checks; `src/reading/overview.ts` (+ test) — overview rules; `src/reading/types.ts` — `Check.related`.
- `src/workspace/Workspace.tsx` (`Head`), `HowToRead.tsx`, `FindingBody.tsx`, `FlowStrip.tsx`, `StoryPage.tsx`, `StoryTabs.tsx`, `Overview.tsx`, `WholePage.tsx`, `Outline.tsx`, `CauseStepper.tsx`.
- e2e: `e2e/helpers.ts` and the specs each task names.

---
## Phase 1 — shared pieces, header, headings, AI marks (spec §1–§4)

### Task 1: The AI mark pieces: hover text, `AiText`, `AiName`, the edge token

**Files:**
- Create: `frontend/src/lib/aiMarks.ts`, `frontend/src/lib/aiMarks.test.ts`, `frontend/src/components/AiText.tsx`
- Modify: `frontend/src/styles.css` (both theme blocks; the AI block), `frontend/src/workspace/workspace.css` (`.vh` moves out)

**Interfaces:**
- Consumes: `AiView` (`src/api.ts`: `strong?: string | null`), `Story` (`src/board/types.ts`: `source?: "tier1" | "rules"`).
- Produces:
  - `aiTitle(by?: string | null): string` — `"Written by AI"` or `"Written by AI · <by>"`.
  - `storyModel(st: Pick<Story, "source">, view: Pick<AiView, "strong"> | null | undefined): string | null` — the strong model's name for a tier-1 story's own text, else `null`.
  - `AiText` (default export of `src/components/AiText.tsx`): props `{ as?: "p" | "li" | "div" | "span"; ai?: boolean; by?: string | null; className?: string; children: ReactNode }` plus any HTML attribute (a `title` passed in replaces the hover). `ai={false}` renders the plain element. Renders class `ai-text`.
  - `AiName` (named export): props `{ ai?: boolean; by?: string | null; title?: string; children: ReactNode }`; renders `span.ai-name` with the hover (`title` replaces it — the overview passes `"Written by AI\n<full name>"` where the name is cut short), or the bare children when `ai={false}`.
  - Global CSS: `--ai-edge`, `.ai-text`, `.vh` (moved from `workspace.css` to `styles.css` so components outside the workspace can use it).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/aiMarks.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { aiTitle, storyModel } from "./aiMarks";

describe("the hover on AI-written text", () => {
  it("says the AI wrote it, naming the model only when the app knows it", () => {
    expect(aiTitle()).toBe("Written by AI");
    expect(aiTitle(null)).toBe("Written by AI");
    expect(aiTitle("fake-strong")).toBe("Written by AI · fake-strong");
  });
  it("names the strong model for a story's own text only when the strong model formed the story", () => {
    expect(storyModel({ source: "tier1" }, { strong: "fake-strong" })).toBe("fake-strong");
    expect(storyModel({ source: "tier1" }, { strong: null })).toBeNull();
    expect(storyModel({ source: "rules" }, { strong: "fake-strong" })).toBeNull();
    expect(storyModel({}, null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/lib/aiMarks.test.ts`
Expected: FAIL — `Failed to resolve import "./aiMarks"`.

- [ ] **Step 3: Write the helpers, the components and the CSS**

Create `frontend/src/lib/aiMarks.ts`:

```ts
import type { AiView } from "../api";
import type { Story } from "../board/types";

/** The hover on AI-written text (spec 2026-10-25-review-ui-redesign §1.2): the model only where the app knows it. */
export const aiTitle = (by?: string | null): string => (by ? `Written by AI · ${by}` : "Written by AI");

/** Who wrote a story's own title, purpose, questions and suggested checks: the strong model, when it formed the story. */
export const storyModel = (st: Pick<Story, "source">, view: Pick<AiView, "strong"> | null | undefined): string | null =>
  st.source === "tier1" ? view?.strong ?? null : null;
```

Create `frontend/src/components/AiText.tsx`:

```tsx
import type { HTMLAttributes, ReactNode } from "react";
import { aiTitle } from "../lib/aiMarks";

type Block = "p" | "li" | "div" | "span";

/** AI-written text (spec 2026-10-25-review-ui-redesign §1.1): a faint edge at its left, who wrote it on hover, and
 * "Written by AI." for screen readers; it renders as the element it replaces. `ai={false}` renders the plain element,
 * so a caller passes its own source test. */
export default function AiText({ as: Tag = "p", ai = true, by, className, children, ...rest }:
  { as?: Block; ai?: boolean; by?: string | null; children: ReactNode } & HTMLAttributes<HTMLElement>) {
  if (!ai) return <Tag className={className} {...rest}>{children}</Tag>;
  return (
    <Tag className={className ? `ai-text ${className}` : "ai-text"} title={aiTitle(by)} {...rest}>
      <span className="vh">Written by AI. </span>{children}
    </Tag>
  );
}

/** An AI-written title or name shown as a heading (§1.1): no edge, the same hover; `title` replaces the hover where the
 * name may be cut short and the hover has to carry the whole of it. */
export function AiName({ ai = true, by, title, children }:
  { ai?: boolean; by?: string | null; title?: string; children: ReactNode }) {
  if (!ai) return <>{children}</>;
  return <span className="ai-name" title={title ?? aiTitle(by)}><span className="vh">Written by AI: </span>{children}</span>;
}
```

In `frontend/src/styles.css`, add the token to the light block — replace

```css
  --add-bg: #e7f5e7; --del-bg: #fbe9e8; --gap-bg: #f1efe9;
```

with

```css
  --add-bg: #e7f5e7; --del-bg: #fbe9e8; --gap-bg: #f1efe9; --ai-edge: #ddd3fb;
```

and to the dark block — replace

```css
  --add-bg: #1e3321; --del-bg: #3a2020; --gap-bg: #26252b;
```

with

```css
  --add-bg: #1e3321; --del-bg: #3a2020; --gap-bg: #26252b; --ai-edge: #4f4378;
```

Still in `styles.css`, directly above the line `/* AI: ✦ buttons, tortoise replies, the @ menu, the AI pill's usage view (spec 2026-10-03 §6) */`, add:

```css
/* read by screen readers only */
.vh { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
/* AI-written text (spec 2026-10-25-review-ui-redesign §1.1): a faint edge at its left; who wrote it is on hover */
.ai-text { border-left: 2px solid var(--ai-edge); padding-left: 10px; }
```

In `frontend/src/workspace/workspace.css`, delete these two lines (the rule now lives in `styles.css`):

```css
/* read by screen readers only: the words between a heading's counts */
.vh { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
```

- [ ] **Step 4: Run the test and the type check**

Run: `cd frontend && npx vitest run src/lib/aiMarks.test.ts && npx tsc --noEmit`
Expected: PASS (2 tests); `tsc` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/aiMarks.ts frontend/src/lib/aiMarks.test.ts frontend/src/components/AiText.tsx frontend/src/styles.css frontend/src/workspace/workspace.css
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(ai): AiText and AiName mark AI-written text with a faint edge and a hover

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 2: The story, its tabs, the overview, the flow strip and the old home page lose their AI chips

**Files:**
- Modify: `frontend/src/workspace/StoryPage.tsx` (imports; `StoryPage` start; both headers' `h2`; the summary), `frontend/src/workspace/StoryTabs.tsx` (imports; `Flows`; `Talk`), `frontend/src/workspace/Overview.tsx` (imports; `ThreadBlock`; the lead), `frontend/src/workspace/FlowStrip.tsx` (imports; the what paragraph; the reason), `frontend/src/workspace/WholePage.tsx` (imports; `OldWhole`'s intent)
- Test: `frontend/e2e/ai.spec.ts`, `frontend/e2e/long-text.spec.ts`, `frontend/e2e/workspace-tier1.spec.ts`, `frontend/e2e/workspace-reading.spec.ts`

**Interfaces:**
- Consumes: `AiText`, `AiName`, `aiTitle`, `storyModel` (Task 1); `useAi()` (`src/lib/ai.tsx`).
- Produces: AI paragraphs carry class `ai-text` and `title="Written by AI"` (or `· <model>`); AI story titles and thread names are wrapped in `span.ai-name`. No `.ai-label` remains in these five files.

- [ ] **Step 1: Point the e2e tests at the edge instead of the chip**

In `frontend/e2e/ai.spec.ts`:

Replace (first test)

```ts
    await expect(what.locator(".ai-label")).toBeVisible();
    await expect(ask).toHaveText("✦ Explain again");
  });

  test("✦ Explain retells a story's title and summary, on the story and in the rail", async ({ page }) => {
```

with

```ts
    await expect(what).toHaveClass(/\bai-text\b/);
    await expect(what).toHaveAttribute("title", "Written by AI");
    await expect(ask).toHaveText("✦ Explain again");
  });

  test("✦ Explain retells a story's title and summary, on the story and in the rail", async ({ page }) => {
```

Replace

```ts
    await expect(head.locator(".ai-label")).toHaveCount(0);                  // this server's up-front pass skips stories
```

with

```ts
    await expect(head.locator("h2 .ai-name")).toHaveCount(0);                // this server's up-front pass skips stories
```

Replace

```ts
    await expect(head.locator("h2 .ai-label")).toBeVisible();                // the title…
    await expect(head.locator(".st-summary .ai-label")).toBeVisible();       // …and the summary, retold
```

with

```ts
    await expect(head.locator("h2 .ai-name")).toHaveAttribute("title", "Written by AI");   // the title…
    await expect(head.locator(".st-summary .ai-text").first()).toBeVisible();              // …and the summary, retold
```

Replace

```ts
    await expect(what.locator(".ai-label")).toBeVisible();                     // the board's narrative, on the story
```

with

```ts
    await expect(what).toHaveClass(/\bai-text\b/);                             // the board's narrative, on the story
```

Replace

```ts
    await expect(lands).toContainText("AI: uart_errors assumes only uart_init writes Uart::errors.");
```

with

```ts
    await expect(lands.locator(".ws-flow-why")).toHaveText("Written by AI. uart_errors assumes only uart_init writes Uart::errors.");
    await expect(lands.locator(".ws-flow-why")).toHaveClass(/\bai-text\b/);
    await expect(lands).not.toContainText("AI:");
```

Replace the last test's opening and its chip checks —

```ts
  test("a story tells the weak model's account: purpose, its flows and what it means, each AI-labelled", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    const purpose = page.locator(".st-summary");
    await expect(purpose.locator(".ai-label")).toBeVisible({ timeout: 30_000 });
```

with

```ts
  test("a story tells the weak model's account: purpose, its flows and what it means, each with the AI edge", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    const purpose = page.locator(".st-summary");
    await expect(purpose.locator(".ai-text")).toBeVisible({ timeout: 30_000 });
    await expect(purpose.locator(".ai-text")).toHaveAttribute("title", "Written by AI");
```

and

```ts
    await expect(cards.locator("> p .ai-label")).toHaveCount(await cards.count());
```

with

```ts
    await expect(cards.locator("> p.ai-text")).toHaveCount(await cards.count());
```

and

```ts
    await expect(effects.locator(".ai-label")).toBeVisible();
    await expect(effects).toContainText("Code that reads Uart::errors now sees transmit errors too.");
```

with

```ts
    await expect(effects.locator(".ai-text")).toBeVisible();
    await expect(effects).toContainText("Code that reads Uart::errors now sees transmit errors too.");
    await expect(page.locator(".ai-label")).toHaveCount(0);
```

In `frontend/e2e/long-text.spec.ts`, replace

```ts
    await expect(page.locator(".st-summary .ai-label")).toBeVisible({ timeout: 30_000 });   // the account is in
```

with

```ts
    await expect(page.locator(".st-summary .ai-text")).toBeVisible({ timeout: 30_000 });    // the account is in
```

In `frontend/e2e/workspace-tier1.spec.ts`, replace

```ts
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveCount(0);       // tier 2 never retells it
```

with

```ts
    await expect(head.locator("h2 .ai-name")).toHaveAttribute("title", "Written by AI · fake-strong");   // the strong model's title
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveCount(0);       // tier 2 never retells it
```

and replace

```ts
  test("the overview's introduction is the strong model's, each part labelled AI", async ({ page }) => {
    await startReview(page);
    const intro = page.locator(".ov-thread").first().locator(".ov-purpose");
    await expect(intro.locator(".ai-label")).toBeVisible();
```

with

```ts
  test("the overview's introduction is the strong model's, its AI parts edged", async ({ page }) => {
    await startReview(page);
    const intro = page.locator(".ov-thread").first().locator(".ov-purpose");
    await expect(intro.first()).toHaveClass(/\bai-text\b/);
```

In `frontend/e2e/workspace-reading.spec.ts`, replace

```ts
    await expect(card.locator(".ov-purpose .ai-label")).toHaveCount(0);
```

with

```ts
    await expect(card.locator(".ov-purpose.ai-text")).toHaveCount(0);
```

- [ ] **Step 2: Build and run the changed specs to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/ai.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-reading.spec.ts`
Expected: FAIL — the new assertions find no `.ai-text` / `.ai-name` (e.g. `ai.spec.ts` "✦ Explain rewrites a flow…": `Expected pattern: /\bai-text\b/`), and `ai.spec.ts` side-effect test still sees `AI:`.

- [ ] **Step 3: Replace the chips**

`frontend/src/workspace/StoryPage.tsx`:

Add to the imports (after `import Explain from "../components/Explain";`):

```tsx
import AiText, { AiName } from "../components/AiText";
import { useAi } from "../lib/ai";
import { storyModel } from "../lib/aiMarks";
```

Replace

```tsx
  const ws = useWs(), d = ws.data, ss = d.stories!;
  // held with its story: another story starts loading, while a refreshed one (AI text) replaces it in place
```

with

```tsx
  const ws = useWs(), d = ws.data, ss = d.stories!, ai = useAi();
  // held with its story: another story starts loading, while a refreshed one (AI text) replaces it in place
```

Replace

```tsx
  const st = detail?.story ?? ss.stories.find((s) => s.id === sid)!;
```

with

```tsx
  const st = detail?.story ?? ss.stories.find((s) => s.id === sid)!;
  const model = storyModel(st, ai?.view);
```

In the old header, replace

```tsx
          {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
        {hasGraph && (
```

with

```tsx
          <AiName ai={st.text_source === "llm"} by={model}><Ticks text={st.title} /></AiName></h2>
        {hasGraph && (
```

In the reading header, replace

```tsx
        {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
      <p className="st-crumb">
```

with

```tsx
        <AiName ai={st.text_source === "llm"} by={model}><Ticks text={st.title} /></AiName></h2>
      <p className="st-crumb">
```

Replace (the summary; the account's purpose is the weak model's, so its hover names no model)

```tsx
        {purpose ? <p><span className="ai-label">AI</span><NameText text={purpose.text} /></p>
          : <p>{st.text_source === "llm" && <span className="ai-label">AI</span>}<NameText text={st.purpose || st.summary} /></p>}
```

with

```tsx
        {purpose ? <AiText><NameText text={purpose.text} /></AiText>
          : <AiText ai={st.text_source === "llm"} by={model}><NameText text={st.purpose || st.summary} /></AiText>}
```

`frontend/src/workspace/StoryTabs.tsx`:

Add to the imports (after `import Comments from "../components/Comments";`):

```tsx
import AiText from "../components/AiText";
import { useAi } from "../lib/ai";
import { storyModel } from "../lib/aiMarks";
```

In `Flows`, replace

```tsx
            {part ? <p><span className="ai-label">AI</span><NameText text={part.text} /></p>
              : <p>{f.what_source === "llm" && <span className="ai-label">AI</span>}<NameText text={f.what} /></p>}
```

with

```tsx
            {part ? <AiText><NameText text={part.text} /></AiText>
              : <AiText ai={f.what_source === "llm"}><NameText text={f.what} /></AiText>}
```

and replace

```tsx
        <p><span className="ai-label">AI</span><NameText text={effects.text} /></p></section>}
```

with

```tsx
        <AiText><NameText text={effects.text} /></AiText></section>}
```

Replace the whole `Talk` function with:

```tsx
/** Talk (§2.4): the strong model's questions and suggested checks, then the story's comment thread. */
function Talk({ detail }: { detail: StoryDetail }) {
  const d = useWs().data, ai = useAi(), st = detail.story, questions = st.questions ?? [], suggested = st.check ?? [];
  const model = storyModel(st, ai?.view);
  return (
    <section aria-labelledby="ws-talk" className="ws-talk">
      <h3 id="ws-talk">Questions and comments</h3>
      {questions.length > 0 && <ul className="st-questions">{questions.map((q, k) => (
        <AiText key={k} as="li" by={model}><NameText text={q} /></AiText>
      ))}</ul>}
      {suggested.length > 0 && <div className="st-suggested"><h4>Also worth checking</h4>
        <AiText as="div" by={model}><ul>{suggested.map((c, k) => <li key={k}><NameText text={c} /></li>)}</ul></AiText></div>}
      <Comments reviewId={d.id} comments={d.comments} kind="story" anchor={{ id: st.id }} onChange={d.loadComments} compact />
    </section>
  );
}
```

`frontend/src/workspace/Overview.tsx`:

Add to the imports (after `import SinkMark from "../components/SinkMark";`):

```tsx
import AiText, { AiName } from "../components/AiText";
import { aiTitle } from "../lib/aiMarks";
```

Replace

```tsx
        <h3>{t.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={t.name} /></h3>
      </header>
      <div className="ov-intro" title={full}>{cardText(t).map((p) => (
        <p key={p.text} className="ov-purpose">{p.ai && <span className="ai-label">AI</span>}<Ticks text={p.text} /></p>
      ))}</div>
```

with (an AI paragraph's own hover would hide the clamped intro's full text, so it carries both)

```tsx
        <h3><AiName ai={t.text_source === "llm"}><Ticks text={t.name} /></AiName></h3>
      </header>
      <div className="ov-intro" title={full}>{cardText(t).map((p) => (
        <AiText key={p.text} className="ov-purpose" ai={p.ai} title={p.ai ? `${aiTitle()}\n${full}` : undefined}>
          <Ticks text={p.text} /></AiText>
      ))}</div>
```

Replace

```tsx
        <p className="ws-lead">{r.whole_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={r.whole} /></p>
```

with

```tsx
        <AiText className="ws-lead" ai={r.whole_source === "llm"}><Ticks text={r.whole} /></AiText>
```

`frontend/src/workspace/FlowStrip.tsx`:

Add to the imports (after `import Comments from "../components/Comments";`):

```tsx
import AiText from "../components/AiText";
```

Replace

```tsx
          {!hideWhat && <p>{flow.what_source === "llm" && <span className="ai-label">AI</span>}<NameText text={flow.what} />{" "}
            <Explain kind="flow" target={flow.id} has={flow.what_source === "llm"} ask={{ kind: "flow", anchor: { id: flow.id }, onAsked: ws.data.loadComments }} /></p>}
```

with

```tsx
          {!hideWhat && <AiText ai={flow.what_source === "llm"}><NameText text={flow.what} />{" "}
            <Explain kind="flow" target={flow.id} has={flow.what_source === "llm"} ask={{ kind: "flow", anchor: { id: flow.id }, onAsked: ws.data.loadComments }} /></AiText>}
```

Replace

```tsx
            {why && <span className="ws-flow-why"> <span className="ai-label">AI</span>AI: <NameText text={why} /></span>}</p>
```

with

```tsx
            {why && <> <AiText as="span" className="ws-flow-why"><NameText text={why} /></AiText></>}</p>
```

`frontend/src/workspace/WholePage.tsx`:

Add to the imports (after `import Comments from "../components/Comments";`):

```tsx
import AiText from "../components/AiText";
```

Replace

```tsx
        {about ? <p className="ws-lead">{about.intent_source === "llm" && <span className="ai-label">AI</span>}<NameText text={about.intent} /></p>
```

with

```tsx
        {about ? <AiText className="ws-lead" ai={about.intent_source === "llm"}><NameText text={about.intent} /></AiText>
```

- [ ] **Step 4: Check, build and run the specs**

Run: `cd frontend && npx tsc --noEmit && grep -n "ai-label" src/workspace/StoryPage.tsx src/workspace/StoryTabs.tsx src/workspace/Overview.tsx src/workspace/FlowStrip.tsx src/workspace/WholePage.tsx; npm run build && E2E e2e/ai.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-reading.spec.ts e2e/long-text.spec.ts`
Expected: `tsc` and `grep` print nothing; all tests in the four specs PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/workspace/StoryPage.tsx frontend/src/workspace/StoryTabs.tsx frontend/src/workspace/Overview.tsx frontend/src/workspace/FlowStrip.tsx frontend/src/workspace/WholePage.tsx frontend/e2e/ai.spec.ts frontend/e2e/long-text.spec.ts frontend/e2e/workspace-tier1.spec.ts frontend/e2e/workspace-reading.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(ai): stories, flows and the overview keep their AI text and lose the AI chips

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 3: Findings, tortoise replies and file summaries lose their AI chips

**Files:**
- Modify: `frontend/src/workspace/FindingBody.tsx` (imports; `VERDICT`; the verdict lines; the analysis section; the hypotheses), `frontend/src/components/Comments.tsx` (imports; `CommentView`; the @ menu row), `frontend/src/components/Explain.tsx` (imports; `FileSummaryView`), `frontend/src/styles.css` (the AI block)
- Test: `frontend/e2e/ai.spec.ts`, `frontend/e2e/workspace-tier1.spec.ts`, `frontend/e2e/workspace-pages.spec.ts`, `frontend/e2e/mention.spec.ts`

**Interfaces:**
- Consumes: `AiText` (Task 1).
- Produces: the finding page's analysis section is labelled `Analysis` (its `h3` keeps the id `${ids}-ai`); verdicts read `Hazard — …`, `Needs review — …`, `No hazard — …`, `No clear hazard — …` inside `AiText`; a tortoise reply's `.comment-body` is an `AiText`; a file summary is `div.ai-text.ai-summary` with `h4` `Summary` and hover `Written by AI · <by>`. After this task no `ai-label` or `ai-tag` exists anywhere in `src/`.

- [ ] **Step 1: Change the e2e tests to the new words and marks**

In `frontend/e2e/ai.spec.ts`, replace

```ts
    const ai = page.getByRole("region", { name: "AI analysis" });
    await expect(ai).toContainText("uart_send can now return -2, and logger_flush drops it.", { timeout: 30_000 });
    await expect(ai.locator(".ai-label")).toBeVisible();
```

with

```ts
    const ai = page.getByRole("region", { name: "Analysis", exact: true });
    await expect(ai).toContainText("uart_send can now return -2, and logger_flush drops it.", { timeout: 30_000 });
    await expect(ai.locator(".ai-text")).toHaveAttribute("title", "Written by AI");
    await expect(page.locator(".ai-label")).toHaveCount(0);
```

Replace

```ts
    await expect(page.locator(".ws-verdict")).toContainText("AI: hazard — uart_errors assumes only uart_init writes Uart::errors.");
```

with

```ts
    await expect(page.locator(".ws-verdict")).toContainText("Hazard — uart_errors assumes only uart_init writes Uart::errors.");
    await expect(page.locator(".ws-verdict")).toHaveClass(/\bai-text\b/);
```

Replace

```ts
    await expect(page.locator(".ws-verdict")).toContainText("AI: no clear hazard — Nothing else depends on the value it writes.");
```

with

```ts
    await expect(page.locator(".ws-verdict")).toContainText("No clear hazard — Nothing else depends on the value it writes.");
```

In the Summarise test, replace

```ts
    await expect(panel).toContainText("Check the readers of uart_errors.");
  });
```

with

```ts
    await expect(panel).toContainText("Check the readers of uart_errors.");
    const summary = panel.locator(".ai-summary");
    await expect(summary).toHaveClass(/\bai-text\b/);
    await expect(summary).toHaveAttribute("title", /^Written by AI · \S+/);
    await expect(summary.locator("h4")).toHaveText("Summary");
  });
```

In `frontend/e2e/workspace-tier1.spec.ts`, replace

```ts
    await expect(hazard).toContainText("AI review: hazard — logger_flush ignores the new -2, so a failed send goes unnoticed.");
```

with

```ts
    await expect(hazard).toContainText("Hazard — logger_flush ignores the new -2, so a failed send goes unnoticed.");
    await expect(hazard).not.toContainText("AI review");
```

and

```ts
    await expect(page.locator(".ws-verdict")).toContainText("AI review: needs review —");
```

with

```ts
    await expect(page.locator(".ws-verdict")).toContainText("Needs review —");
```

In `frontend/e2e/workspace-pages.spec.ts`, replace

```ts
    await expect(page.getByRole("region", { name: "AI analysis" })).toContainText("AI analysis unavailable.");
```

with

```ts
    await expect(page.getByRole("region", { name: "Analysis", exact: true })).toContainText("No analysis: AI is not set up.");
```

replace

```ts
    const ai = page.getByRole("region", { name: "AI analysis" });
```

with

```ts
    const ai = page.getByRole("region", { name: "Analysis", exact: true });
```

and replace

```ts
    await expect(ai).toContainText("AI analysis unavailable.");
```

with

```ts
    await expect(ai).toContainText("No analysis: AI is not set up.");
```

In `frontend/e2e/mention.spec.ts`, replace

```ts
    await expect(reply.locator(".ai-label")).toHaveText("AI");
```

with

```ts
    await expect(reply.locator(".comment-body")).toHaveClass(/\bai-text\b/);
    await expect(reply.locator(".ai-label")).toHaveCount(0);
```

- [ ] **Step 2: Build and run the changed specs to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/ai.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-pages.spec.ts e2e/mention.spec.ts`
Expected: FAIL — no region named `Analysis` exactly, verdicts still start `AI: ` / `AI review: `, `.comment-body` and `.ai-summary` have no `ai-text` class.

- [ ] **Step 3: Replace the chips**

`frontend/src/workspace/FindingBody.tsx`:

Add to the imports (after `import Comments from "../components/Comments";`):

```tsx
import AiText from "../components/AiText";
```

Replace

```tsx
const VERDICT = { hazard: "hazard", needs_review: "needs review", no_hazard: "no hazard" } as const;
```

with

```tsx
const VERDICT = { hazard: "Hazard", needs_review: "Needs review", no_hazard: "No hazard" } as const;
```

Replace the verdict block — from

```tsx
      {f.verdict_source === "tier1" && f.verdict ? (
        <p className={`ws-verdict ${f.verdict}`}>
          <span className="ai-label">AI</span>AI review: {VERDICT[f.verdict]} — <NameText text={f.verdict_reason ?? ""} />
```

to

```tsx
      {f.verdict_source === "tier1" && f.verdict ? (
        <AiText className={`ws-verdict ${f.verdict}`}>
          {VERDICT[f.verdict]} — <NameText text={f.verdict_reason ?? ""} />
```

then, a few lines down, replace

```tsx
          })}</span>}
        </p>
      ) : f.side_effect && (
        <p className={`ws-verdict${f.verdict === "hazard" ? " hazard" : ""}`}>
          {f.verdict === "hazard" ? <><span className="ai-label">AI</span>AI: hazard — <NameText text={f.verdict_reason ?? ""} /></>
            : f.verdict === "no_hazard" ? <><span className="ai-label">AI</span>AI: no clear hazard — <NameText text={f.verdict_reason ?? ""} /></>
            : <>Side effect · not yet assessed. Side effects are normal; ✦ Explain asks the AI whether this one is a hazard.</>}
        </p>
      )}
```

with

```tsx
          })}</span>}
        </AiText>
      ) : f.side_effect && (
        f.verdict === "hazard" ? <AiText className="ws-verdict hazard">Hazard — <NameText text={f.verdict_reason ?? ""} /></AiText>
          : f.verdict === "no_hazard" ? <AiText className="ws-verdict">No clear hazard — <NameText text={f.verdict_reason ?? ""} /></AiText>
          : <p className="ws-verdict">Side effect · not yet assessed. Side effects are normal; Explain asks whether this one is a hazard.</p>
      )}
```

Replace the analysis section

```tsx
      <h3 id={`${ids}-ai`}>AI analysis</h3>
      {f.explanation ? <p><span className="ai-label">AI</span><NameText text={f.explanation} /> <Explain kind="finding" target={f.id} has ask={talk} /></p>
        : !ai?.view ? <p className="muted">Checking for AI analysis…</p>
        : !ai.view.llm ? <p className="muted">AI analysis unavailable.</p>
```

with

```tsx
      <h3 id={`${ids}-ai`}>Analysis</h3>
      {f.explanation ? <AiText><NameText text={f.explanation} /> <Explain kind="finding" target={f.id} has ask={talk} /></AiText>
        : !ai?.view ? <p className="muted">Checking for an analysis…</p>
        : !ai.view.llm ? <p className="muted">No analysis: AI is not set up.</p>
```

Replace

```tsx
          <li key={k}><span className="ai-label">AI</span><NameText text={h.text} />
            {h.cites.filter((c) => c.startsWith("N")).length > 0 && <span className="muted"> — {h.cites.filter((c) => c.startsWith("N")).map((c, j) => <span key={c}>{j > 0 && ", "}{name(c)}</span>)}</span>}</li>
```

with

```tsx
          <AiText key={k} as="li"><NameText text={h.text} />
            {h.cites.filter((c) => c.startsWith("N")).length > 0 && <span className="muted"> — {h.cites.filter((c) => c.startsWith("N")).map((c, j) => <span key={c}>{j > 0 && ", "}{name(c)}</span>)}</span>}</AiText>
```

`frontend/src/components/Comments.tsx`:

Add to the imports (after `import Logo from "./Logo";`):

```tsx
import AiText from "./AiText";
```

In `CommentView`, delete the line

```tsx
        {ai && <span className="ai-label">AI</span>}
```

and replace

```tsx
        <div className="comment-body">{c.body}</div>
```

with

```tsx
        <AiText as="div" ai={ai} className="comment-body">{c.body}</AiText>
```

In the @ menu, replace

```tsx
              <b>@{o.name}</b>{o.ai && <span className="ai-label">AI</span>}
```

with

```tsx
              <b>@{o.name}</b>
```

`frontend/src/components/Explain.tsx`:

Add to the imports (after `import { aiAvailability, callTitle, jobFor } from "../lib/aiState";`):

```tsx
import AiText from "./AiText";
```

Replace the whole `FileSummaryView` function with:

```tsx
/** A file's AI summary, above its code (spec 2026-10-25-review-ui-redesign §4): the edge, and its model on hover. */
export function FileSummaryView({ path }: { path: string }) {
  const s = useAi()?.view?.file_summaries[path];
  if (!s || !s.summary) return null;
  return (
    <AiText as="div" by={s.by} className="ai-summary">
      <h4>Summary</h4>
      <p>{s.summary}</p>
      {s.check.length > 0 && <><b>Check</b><ol>{s.check.map((c, i) => <li key={i}>{c}</li>)}</ol></>}
    </AiText>
  );
}
```

`frontend/src/styles.css` — delete the chip rules

```css
.ai-label { display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: .05em; padding: 0 5px; margin-right: 5px;
  border-radius: 4px; background: #6d55e8; color: #fff; vertical-align: 1px; }
```

and

```css
.ai-tag { font-size: 11px; color: var(--muted); }
```

and replace

```css
.ai-summary { margin: 6px 10px; padding: 8px 10px; border-left: 3px solid #8f75ff; background: var(--surface); font-size: 13px; }
```

with

```css
.ai-summary { margin: 6px 10px; padding: 8px 10px; background: var(--surface); font-size: 13px; }
.ai-summary h4 { margin: 0 0 4px; }
```

- [ ] **Step 4: Check, build and run the specs**

Run: `cd frontend && npx tsc --noEmit && grep -rn "ai-label\|ai-tag" src; npm run build && E2E e2e/ai.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-pages.spec.ts e2e/mention.spec.ts`
Expected: `tsc` and `grep` print nothing; all four specs PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/workspace/FindingBody.tsx frontend/src/components/Comments.tsx frontend/src/components/Explain.tsx frontend/src/styles.css frontend/e2e/ai.spec.ts frontend/e2e/workspace-tier1.spec.ts frontend/e2e/workspace-pages.spec.ts frontend/e2e/mention.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(ai): findings, tortoise replies and file summaries say what they are without an AI chip

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 4: One `Explain ▾` menu instead of the ✦ pill and the Ask… link

**Files:**
- Create: `frontend/src/lib/useMenu.ts`
- Modify: `frontend/src/components/Explain.tsx` (the `Explain` component), `frontend/src/styles.css` (`.ai-btn`; new `.ai-menuwrap`, `.ai-menu`), `frontend/e2e/helpers.ts` (new `explainItem`)
- Test: `frontend/e2e/ai.spec.ts`, `frontend/e2e/mention.spec.ts`

**Interfaces:**
- Consumes: `callTitle`, `aiAvailability`, `jobFor` (`src/lib/aiState.ts`), `useAi()`.
- Produces:
  - `useMenu<M extends HTMLElement = HTMLElement>(open: boolean, close: () => void): { button: RefObject<HTMLButtonElement | null>; menu: RefObject<M | null> }` — attach `button` to the menu button and `menu` to the `role="menu"` element. While `open`: the first enabled `[role="menuitem"]` takes focus; ArrowDown/ArrowUp (wrapping), Home, End move focus while it is inside the menu; Escape calls `close()` and focuses the button; a pointerdown outside both calls `close()`. Task 6's ⋯ menu uses it too.
  - `Explain` (same props as today): a button named `Explain` (or the caller's `label`, e.g. `Summarise`; `Explaining…`/`Summarising…` while its job runs) with `aria-haspopup="menu"`, opening a `role="menu"` of `menuitem`s: the explain item (`Explain`, `Explain again`, `Summarise`, `Summarise again`; disabled while running; `title` = `callTitle`) and `Ask a question…` when `ask` is given. With `askOnly`, a button `Ask…` toggles the question box directly.
  - e2e helper `explainItem(scope: Locator, item: string | RegExp): Promise<void>` — opens the first Explain/Summarise menu in `scope` and picks `item` (a string matches exactly).

- [ ] **Step 1: Point the e2e tests at the menu**

In `frontend/e2e/helpers.ts`, add at the end:

```ts
/** Pick an item of the first Explain ▾ (or Summarise ▾) menu inside `scope` (spec 2026-10-25-review-ui-redesign §4.1). */
export async function explainItem(scope: Locator, item: string | RegExp) {
  await scope.getByRole("button", { name: /^(Explain|Summarise)$/ }).first().click();
  await scope.getByRole("menuitem", typeof item === "string" ? { name: item, exact: true } : { name: item }).click();
}
```

In `frontend/e2e/ai.spec.ts`, change the import line to

```ts
import { contrast, explainItem, login, openIndex, startReview } from "./helpers";
```

Replace the whole first test (`"✦ Explain rewrites a flow that the up-front pass left"`) with:

```ts
  test("Explain rewrites a flow that the up-front pass left", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?view=graph&flow=2`);
    const what = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text p").first();
    const button = what.getByRole("button", { name: "Explain", exact: true });
    await expect(button).toHaveAttribute("aria-haspopup", "menu");
    await button.click();
    const item = what.getByRole("menuitem", { name: "Explain", exact: true });
    await expect(item).toHaveAttribute("title", /^1 AI call · \d+ left on this review$/);
    await expect(what).not.toContainText("reaches logger_flush, which drops it");
    await item.click();
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await expect(what).toHaveClass(/\bai-text\b/);
    await expect(what).toHaveAttribute("title", "Written by AI");
    await button.click();
    await expect(what.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
    await page.keyboard.press("Escape");                                     // Escape closes it and returns to the button
    await expect(what.getByRole("menu")).toHaveCount(0);
    await expect(button).toBeFocused();
  });
```

In the story test, replace

```ts
  test("✦ Explain retells a story's title and summary, on the story and in the rail", async ({ page }) => {
```

with

```ts
  test("Explain retells a story's title and summary, on the story and in the rail", async ({ page }) => {
```

replace

```ts
    await head.getByRole("button", { name: "✦ Explain" }).click();
    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
    await expect(head.locator("h2 .ai-name")).toHaveAttribute("title", "Written by AI");   // the title…
```

with

```ts
    await explainItem(head, "Explain");
    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
    await expect(head.locator("h2 .ai-name")).toHaveAttribute("title", "Written by AI");   // the title…
```

and replace

```ts
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
```

with

```ts
    await head.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(head.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
    await page.keyboard.press("Escape");
```

In the graph test, replace

```ts
  test("✦ Explain on a story with its graph open neither flashes Loading nor redraws the graph", async ({ page }) => {
```

with

```ts
  test("Explain on a story with its graph open neither flashes Loading nor redraws the graph", async ({ page }) => {
```

and

```ts
    await head.getByRole("button", { name: "✦ Explain" }).click();
```

with

```ts
    await explainItem(head, "Explain");
```

In the narrative test, replace

```ts
  test("a story shows the flow narrative the up-front pass wrote, and ✦ Explain on another flow updates it", async ({ page }) => {
```

with

```ts
  test("a story shows the flow narrative the up-front pass wrote, and Explain on another flow updates it", async ({ page }) => {
```

replace

```ts
    await expect(what.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
    const other = ss.stories.flatMap((x: { id: string; flows: string[] }) => x.flows.map((f) => [x.id, f]))
```

with

```ts
    await what.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(what.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
    const other = ss.stories.flatMap((x: { id: string; flows: string[] }) => x.flows.map((f) => [x.id, f]))
```

and replace

```ts
    const ask = what.getByRole("button", { name: /Explain/ });
    await expect(ask).toHaveText("✦ Explain");
    await ask.click();
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await expect(ask).toHaveText("✦ Explain again");
```

with

```ts
    await explainItem(what, "Explain");
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await what.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(what.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
```

In the finding test, replace

```ts
    await expect(ai.getByRole("button", { name: /Explain again/ })).toBeVisible();
```

with

```ts
    await ai.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(ai.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
```

In the Summarise test, replace

```ts
  test("✦ Summarise sums up a file in its diff", async ({ page }) => {
```

with

```ts
  test("Summarise sums up a file in its diff", async ({ page }) => {
```

and

```ts
    await panel.getByRole("button", { name: /Summarise/ }).click();
```

with

```ts
    await explainItem(panel, "Summarise");
```

In `frontend/e2e/mention.spec.ts`, change the import line to

```ts
import { explainItem, openIndex, startReview } from "./helpers";
```

replace

```ts
  test("Ask… on an explain button puts the question to tortoise in a thread on that finding, story, flow or file", async ({ page }) => {
    const base = await startReview(page);
    const ask = async (where: Locator, question: string) => {
      await where.getByRole("button", { name: "Ask…" }).first().click();
```

with

```ts
  test("Ask a question… in an Explain menu puts the question to tortoise in a thread on that finding, story, flow or file", async ({ page }) => {
    const base = await startReview(page);
    const ask = async (where: Locator, question: string) => {
      await explainItem(where, "Ask a question…");
```

and replace

```ts
    await expect(page.getByRole("button", { name: /✦/ })).toHaveCount(0);
```

with

```ts
    await expect(page.getByRole("button", { name: /^(Explain|Summarise|Ask…)$/ })).toHaveCount(0);
```

- [ ] **Step 2: Build and run the two specs to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/ai.spec.ts e2e/mention.spec.ts`
Expected: FAIL — no button named exactly `Explain` (today's is `✦ Explain`) and no `menuitem`.

- [ ] **Step 3: Write `useMenu` and the menu**

Create `frontend/src/lib/useMenu.ts`:

```ts
import { type RefObject, useEffect, useRef } from "react";

/** A popup menu's behaviour (WAI-ARIA menu button): opening focuses its first enabled item; ArrowDown, ArrowUp, Home and
 * End move between items while focus is in the menu; Escape closes it and returns focus to its button; a press outside
 * the menu and its button closes it. */
export function useMenu<M extends HTMLElement = HTMLElement>(open: boolean, close: () => void):
    { button: RefObject<HTMLButtonElement | null>; menu: RefObject<M | null> } {
  const button = useRef<HTMLButtonElement>(null), menu = useRef<M>(null);
  const shut = useRef(close);
  shut.current = close;
  useEffect(() => {
    if (!open) return;
    const items = () => [...(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? [])];
    items()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); shut.current(); button.current?.focus(); return; }
      const all = items(), at = all.indexOf(document.activeElement as HTMLElement);
      if (at < 0) return;                                  // focus is elsewhere: the keys are not the menu's
      const to = { ArrowDown: (at + 1) % all.length, ArrowUp: (at - 1 + all.length) % all.length, Home: 0, End: all.length - 1 }[e.key];
      if (to !== undefined) { e.preventDefault(); all[to].focus(); }
    };
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !button.current?.contains(t)) shut.current();
    };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", away);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", away); };
  }, [open]);
  return { button, menu };
}
```

In `frontend/src/components/Explain.tsx`, add to the imports (after `import { aiAvailability, callTitle, jobFor } from "../lib/aiState";`):

```tsx
import { useMenu } from "../lib/useMenu";
```

and replace the whole `Explain` function (from its doc comment `/** ✦ Explain / ✦ Summarise …` to its closing `}`) with:

```tsx
/** Explain ▾ (spec 2026-10-25-review-ui-redesign §4.1): a small menu of Explain — or the caller's label, "again" once
 * the item has a result — and Ask a question…; one AI call, shown to everyone. An item the strong model wrote allows
 * only Ask… (two-tier stories §8). A refusal or failure, and the sent note, show beside it. */
export default function Explain({ kind, target, has, label = "Explain", ask, askOnly = false }: Props) {
  const ai = useAi();
  const [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const { button, menu } = useMenu<HTMLSpanElement>(open, () => setOpen(false));
  if (!ai?.view?.llm) return null;
  const can = aiAvailability(ai.view);
  const send = () => {
    const q = question.trim();
    if (!q || !ask) return;
    setSent(null);
    api.addComment(ai.reviewId, `@tortoise ${q}`, ask.kind, ask.anchor)
      .then(() => { setQuestion(""); setAsking(false); setSent("Asked: the answer comes in this item's thread."); ask.onAsked(); })
      .catch((x) => setSent(String(x.message ?? x)));
  };
  const job = jobFor(ai.view, kind, target);
  const running = job?.status === "running";
  const asked = ai.asked[`${kind}:${target}`];
  const failed = asked ?? (job && (job.status === "failed" || job.status === "refused")
    ? { error: job.error ?? "the AI call failed", refused: job.status === "refused" || REFUSED.test(job.error ?? "") } : null);
  const what = kind === "file" ? "summary" : "explanation";
  const doing = `${label === "Explain" ? "Explaining" : "Summarising"}…`;
  const run = () => {
    setOpen(false);
    button.current?.focus();
    if (!has || window.confirm(`Replace the current ${what}? It costs 1 AI call.`)) ai.explain(kind, target);
  };
  return (
    <span className="ai-ask" onClick={(e) => e.stopPropagation()}>
      {askOnly ? ask && (
        <button className="ai-btn" aria-expanded={asking} title="Ask the AI something specific about this; it answers in a thread"
                onClick={() => setAsking(!asking)}>Ask…</button>
      ) : (
        <span className="ai-menuwrap">
          <button ref={button} className="ai-btn" aria-haspopup="menu" aria-expanded={open} title="Ask the AI about this"
                  onClick={() => setOpen(!open)}>{running ? doing : label}<span aria-hidden> ▾</span></button>
          {open && (
            <span className="ai-menu" role="menu" aria-label={label} ref={menu}>
              <button role="menuitem" disabled={running} title={callTitle(ai.view)} onClick={run}>
                {running ? doing : has ? `${label} again` : label}</button>
              {ask && <button role="menuitem" onClick={() => { setOpen(false); setAsking(true); }}>Ask a question…</button>}
            </span>
          )}
        </span>
      )}
      {ask && asking && (
        <span className="ai-askq">
          <textarea aria-label="What should the AI explain?" rows={2} value={question} autoFocus
                    placeholder="What should it explain? @tortoise answers in a thread here."
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }} />
          <button className="ai-btn" disabled={!question.trim() || !can.ok} title={can.detail} onClick={send}>Ask</button>
        </span>
      )}
      {sent && !asking && <span className="muted small" role="status">{sent}</span>}
      {failed && !running && (
        <span className="ai-err" role="alert">
          {failed.error}
          {failed.refused && ai.view.is_owner && (
            <button className="link small" onClick={() => ai.setUsageOpen(true)}>Raise budget</button>
          )}
        </span>
      )}
    </span>
  );
}
```

In `frontend/src/styles.css`, replace

```css
.ai-btn { font-size: 12px; padding: 1px 8px; border-radius: 99px; border: 1px solid #8f75ff; background: transparent; color: inherit;
  cursor: pointer; white-space: nowrap; }
.ai-btn:hover:not(:disabled) { background: rgba(143,117,255,.15); } .ai-btn:disabled { opacity: .6; cursor: default; }
```

with

```css
.ai-btn { font-size: 12px; padding: 1px 8px; border-radius: 6px; border: 1px solid var(--line); background: var(--surface); color: inherit;
  cursor: pointer; white-space: nowrap; }
.ai-btn:hover:not(:disabled) { background: var(--gap-bg); } .ai-btn:disabled { opacity: .6; cursor: default; }
/* Explain ▾ (spec 2026-10-25-review-ui-redesign §4.1) */
.ai-menuwrap { position: relative; display: inline-flex; }
.ai-menu { position: absolute; top: calc(100% + 4px); left: 0; z-index: 40; display: flex; flex-direction: column; min-width: 170px;
  padding: 4px 0; background: var(--surface); color: var(--ink); border: 1px solid var(--line); border-radius: 8px;
  box-shadow: 0 6px 18px rgba(0,0,0,.14); font-size: 13px; }
.ai-menu [role="menuitem"] { border: 0; border-radius: 0; background: none; padding: 5px 12px; text-align: left; white-space: nowrap; }
.ai-menu [role="menuitem"]:hover:not(:disabled), .ai-menu [role="menuitem"]:focus-visible { background: var(--gap-bg); }
```

- [ ] **Step 4: Check, build and run the specs**

Run: `cd frontend && npx tsc --noEmit && npm run build && E2E e2e/ai.spec.ts e2e/mention.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-pages.spec.ts`
Expected: `tsc` prints nothing; all four specs PASS (tier1's `Ask…` button and the pages spec's "Explain only once the AI is known" still hold).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/useMenu.ts frontend/src/components/Explain.tsx frontend/src/styles.css frontend/e2e/helpers.ts frontend/e2e/ai.spec.ts frontend/e2e/mention.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(ai): Explain and Ask share one small Explain menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 5: Section headings become dark sentence-case titles

**Files:**
- Modify: `frontend/src/styles.css` (global `h4`; `.rv-head h2`), `frontend/src/workspace/workspace.css` (`.ov-band h3`, `.ws-sec-t`, `.ws-whole`, `.ws-nb-col h3`/`.ws-tree-sec h3`, `.ws-steps h3`, `.ws-finding`, `.st-suggested h4`)
- Test: `frontend/e2e/workspace-pages.spec.ts` (new test)

**Interfaces:**
- Consumes: nothing new.
- Produces: the §1.3 style on `.ws-whole h2` · `.ws-finding h3` · `.ws-steps h3` · `.ws-nb-col h3` · `.ws-tree-sec h3` · global `h4` · `.ws-sec-t` · `.rv-head h2` · `.ov-band h3`: `text-transform: none`, `letter-spacing: normal`, `font-weight: 650`, `color: var(--ink)`, 16px (`h2`) or 15px (`h3`, `h4`, `.ws-sec-t`), margin `20px 0 6px` where the heading sits in a page's flow. Micro-labels (`.bd-tag`, `.bd-blabel`, node kind labels, toolbar labels, `.bd-layer-thread .m`, `.bd-ann .k`, `.ws-file-tools .act`, `.ws-cgroup h4`, `.st-clgroup h4`) keep their own rules.

- [ ] **Step 1: Write the failing e2e test**

In `frontend/e2e/workspace-pages.spec.ts`, inside `test.describe("desktop", …)`, add after the first test:

```ts
  test("section headings are dark sentence-case titles, not grey capitals", async ({ page }) => {
    const base = await startReview(page);
    const look = (selector: string) => page.locator(selector).first().evaluate((el) => {
      const cs = getComputedStyle(el);
      return [cs.textTransform, cs.letterSpacing, cs.fontWeight, cs.fontSize, cs.color === getComputedStyle(document.body).color];
    });
    await expect(page.locator(".ws-whole h2").first()).toBeVisible();
    expect(await look(".ws-whole h2")).toEqual(["none", "normal", "650", "16px", true]);
    await page.goto(`${base}/f/F4?details=1`);
    await expect(page.locator(".ws-finding h3").first()).toBeVisible();
    expect(await look(".ws-finding h3")).toEqual(["none", "normal", "650", "15px", true]);
    await page.goto("/");
    await expect(page.locator(".rv-head h2")).toBeVisible();
    expect(await look(".rv-head h2")).toEqual(["none", "normal", "650", "16px", true]);
  });
```

- [ ] **Step 2: Build and run it to watch it fail**

Run: `cd frontend && npm run build && E2E e2e/workspace-pages.spec.ts -g "section headings"`
Expected: FAIL — `Expected: ["none", "normal", "650", "16px", true]`, `Received: ["uppercase", "0.65px", "700", "13px", false]` (or similar grey-capital values).

- [ ] **Step 3: Restyle the headings**

In `frontend/src/styles.css`, replace

```css
h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 12px 0 4px; }
```

with

```css
/* section headings (spec 2026-10-25-review-ui-redesign §1.3): dark, sentence case, carrying the point */
h4 { font-size: 15px; font-weight: 650; color: var(--ink); margin: 20px 0 6px; }
```

and replace

```css
.rv-head h2 { margin: 0; font-size: 13px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
```

with (the heading shares a flex row with the search box, so it keeps no margin)

```css
.rv-head h2 { margin: 0; font-size: 16px; font-weight: 650; color: var(--ink); }
```

In `frontend/src/workspace/workspace.css`, replace

```css
.ov-band h3 { width: 92px; flex: none; margin: 4px 0 0; font: 700 11px var(--bd-sans); letter-spacing: .06em;
  text-transform: uppercase; color: var(--bd-band-label); }
```

with

```css
.ov-band h3 { width: 92px; flex: none; margin: 4px 0 0; font: 650 15px var(--bd-sans); color: var(--ink); }
```

replace

```css
.ws-sec-t { display: flex; align-items: center; gap: 6px; width: 100%; border: 0; background: none; border-radius: 0;
  padding: 7px 14px; font: 600 12px/1.3 var(--sans); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); text-align: left; }
```

with

```css
.ws-sec-t { display: flex; align-items: center; gap: 6px; width: 100%; border: 0; background: none; border-radius: 0;
  padding: 7px 14px; font: 650 15px/1.3 var(--sans); color: var(--ink); text-align: left; }
```

replace

```css
.ws-whole > section { margin: 0 0 26px; }
```

with

```css
.ws-whole > section { margin: 0 0 6px; }
.ws-whole > section:first-child > h2:first-child { margin-top: 0; }
```

replace

```css
.ws-whole h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 0 0 8px; }
```

with

```css
.ws-whole h2 { font-size: 16px; font-weight: 650; color: var(--ink); margin: 20px 0 6px; }
```

replace

```css
.ws-nb-col h3, .ws-tree-sec h3 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
```

with

```css
.ws-nb-col h3, .ws-tree-sec h3 { margin: 20px 0 6px; font-size: 15px; font-weight: 650; color: var(--ink); }
```

replace

```css
.ws-steps h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 20px 0 6px; }
```

with

```css
.ws-steps h3 { font-size: 15px; font-weight: 650; color: var(--ink); margin: 20px 0 6px; }
```

replace

```css
.ws-finding section { margin: 0 0 20px; }
.ws-finding h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 0 0 6px; }
```

with

```css
.ws-finding section { margin: 0; }
.ws-finding h3 { font-size: 15px; font-weight: 650; color: var(--ink); margin: 20px 0 6px; }
```

and delete (the global `h4` now styles "Also worth checking")

```css
.st-suggested h4 { margin: 0 0 4px; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: none; letter-spacing: 0; }
```

- [ ] **Step 4: Build and run the specs that read headings**

Run: `cd frontend && npm run build && E2E e2e/workspace-pages.spec.ts e2e/workspace.spec.ts e2e/landing.spec.ts e2e/long-text.spec.ts`
Expected: PASS (the long-text spec confirms the larger headings still fit their boxes).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles.css frontend/src/workspace/workspace.css frontend/e2e/workspace-pages.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "style(workspace): section headings are dark sentence-case titles instead of grey capitals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 6: One quiet header row and its ⋯ menu

**Files:**
- Create: `frontend/src/workspace/reviewMenu.ts`, `frontend/src/workspace/reviewMenu.test.ts`, `frontend/src/workspace/ReviewMenu.tsx`, `frontend/e2e/header-menu.spec.ts`
- Modify: `frontend/src/reading/causes.ts` (`progressLine`), `frontend/src/reading/causes.test.ts`, `frontend/src/lib/aiState.ts` (`nearLimit`), `frontend/src/lib/aiState.test.ts`, `frontend/src/components/HeadlinePill.tsx`, `frontend/src/components/AiPill.tsx`, `frontend/src/workspace/HowToRead.tsx`, `frontend/src/workspace/Workspace.tsx` (imports; `Head`), `frontend/src/styles.css`, `frontend/src/workspace/workspace.css`, `frontend/e2e/helpers.ts`
- Test: also `frontend/e2e/ai.spec.ts`, `mention.spec.ts`, `workspace-tier1.spec.ts`, `workspace-story.spec.ts`, `outline-causes.spec.ts`, `workspace-reading.spec.ts`, `workspace-plan.spec.ts`, `workspace.spec.ts`, `landing.spec.ts`

**Interfaces:**
- Consumes: `useMenu` (Task 4); `driftSummary` (`src/board/drift.ts`); `useMe` (`src/App`); `api.rerun(id, fresh?)`.
- Produces:
  - `progressLine(read, stories, open, total)` says `N checks open` / `1 check open` / `every check done`.
  - `nearLimit(v: AiView | null | undefined): boolean` — `!!v?.llm && v.used >= v.budget * 0.9`.
  - `reviewMenu.ts`: `type MenuId = "drift" | "notes" | "ai" | "help" | "rerun" | "fresh"`; `interface MenuItem { id: MenuId; label: string }`; `interface MenuState { drift: number; notes: { failed: number; degraded: number }; ai: { used: number; budget: number } | null; reading: boolean; owner: boolean; ready: boolean; strong: boolean }`; `menuItems(m: MenuState): MenuItem[]`; `menuAttention(m: MenuState): string | null`.
  - `ReviewMenu({ under }: { under: () => number })` — `under()` gives the viewport y just below the header, where the menu and its panels open.
  - `AiPill()` renders only near the limit; `Usage({ onClose, top }: { onClose: () => void; top: number })` is exported and rendered by `Head`.
  - `HowToRead({ top }: { top: number })` is the panel only (no `?` button).
  - e2e helpers `reviewMenu(page: Page): Promise<Locator>` (opens ⋯ unless open; returns the menu) and `openAiUsage(page: Page): Promise<Locator>` (returns the `AI usage` dialog).

- [ ] **Step 1: Write the failing unit tests**

In `frontend/src/reading/causes.test.ts`, replace

```ts
  it("counts stories read and the open causes", () => {
    expect(progressLine(3, 9, 12, 20)).toBe("3 of 9 stories read · 12 causes open");
    expect(progressLine(3, 9, 1, 20)).toBe("3 of 9 stories read · 1 cause open");
```

with

```ts
  it("counts stories read and the open checks", () => {
    expect(progressLine(3, 9, 12, 20)).toBe("3 of 9 stories read · 12 checks open");
    expect(progressLine(3, 9, 1, 20)).toBe("3 of 9 stories read · 1 check open");
```

In `frontend/src/lib/aiState.test.ts`, change the import to

```ts
import { aiAvailability, callTitle, finished, jobFor, nearLimit } from "./aiState";
```

and add at the end of the file:

```ts
describe("nearLimit", () => {
  it("shows the AI pill from 90% of the review's budget, and never without an AI", () => {
    expect(nearLimit(view({ used: 179, budget: 200 }))).toBe(false);
    expect(nearLimit(view({ used: 180, budget: 200 }))).toBe(true);
    expect(nearLimit(view({ used: 200, budget: 200, llm: false }))).toBe(false);
    expect(nearLimit(null)).toBe(false);
  });
});
```

Create `frontend/src/workspace/reviewMenu.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { menuAttention, menuItems, type MenuState } from "./reviewMenu";

const state = (over: Partial<MenuState> = {}): MenuState => ({
  drift: 0, notes: { failed: 0, degraded: 0 }, ai: null, reading: true, owner: true, ready: true, strong: false, ...over });

describe("the review menu", () => {
  it("lists what moved out of the header, each only when it applies, in order", () => {
    expect(menuItems(state({ drift: 18, notes: { failed: 1, degraded: 2 }, ai: { used: 6, budget: 200 }, strong: true }))
      .map((i) => i.label)).toEqual(["Workspace drift · 18", "Stage notes · 3", "AI calls used · 6 of 200",
                                     "How to read this page", "Re-run", "Re-run stories, fresh"]);
  });
  it("leaves out the AI line without an AI and the help without a reading", () => {
    expect(menuItems(state({ reading: false })).map((i) => i.id)).toEqual(["rerun"]);
  });
  it("offers Re-run to the owner of a finished review only, and fresh stories only with a strong model", () => {
    expect(menuItems(state({ owner: false, strong: true })).map((i) => i.id)).toEqual(["help"]);
    expect(menuItems(state({ ready: false, strong: true })).map((i) => i.id)).toEqual(["help"]);
    expect(menuItems(state()).map((i) => i.id)).toEqual(["help", "rerun"]);
  });
  it("lights the dot for drift or a failed stage, not for a degraded one, and says why", () => {
    expect(menuAttention(state())).toBeNull();
    expect(menuAttention(state({ notes: { failed: 0, degraded: 2 } }))).toBeNull();
    expect(menuAttention(state({ drift: 3 }))).toBe("workspace drift");
    expect(menuAttention(state({ drift: 3, notes: { failed: 1, degraded: 0 } }))).toBe("workspace drift, a stage failed");
  });
});
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npx vitest run src/reading/causes.test.ts src/lib/aiState.test.ts src/workspace/reviewMenu.test.ts`
Expected: FAIL — `progressLine` still says "causes", `nearLimit` is not exported, `./reviewMenu` does not resolve.

- [ ] **Step 3: Write the rules**

In `frontend/src/reading/causes.ts`, replace

```ts
  return `${head} · ${open ? `${open} cause${open === 1 ? "" : "s"} open` : "every check done"}`;
```

with

```ts
  return `${head} · ${open ? `${open} check${open === 1 ? "" : "s"} open` : "every check done"}`;
```

In `frontend/src/lib/aiState.ts`, add after `callTitle`:

```ts
/** The header's AI pill shows only near the review's limit (spec 2026-10-25-review-ui-redesign §2.1). */
export const nearLimit = (v: AiView | null | undefined): boolean => !!v?.llm && v.used >= v.budget * 0.9;
```

Create `frontend/src/workspace/reviewMenu.ts`:

```ts
/** The review header's ⋯ menu (spec 2026-10-25-review-ui-redesign §2.2): what moved out of the header row. */
export type MenuId = "drift" | "notes" | "ai" | "help" | "rerun" | "fresh";
export interface MenuItem { id: MenuId; label: string }
export interface MenuState {
  drift: number;                                  // workspace drift lines (warnings)
  notes: { failed: number; degraded: number };    // stages that failed or degraded
  ai: { used: number; budget: number } | null;    // null: no AI configured
  reading: boolean;                               // the review has a reading
  owner: boolean;
  ready: boolean;
  strong: boolean;                                // a strong model is configured
}

/** The items, each only when it applies, in the spec's order. */
export function menuItems(m: MenuState): MenuItem[] {
  const out: MenuItem[] = [], notes = m.notes.failed + m.notes.degraded;
  if (m.drift > 0) out.push({ id: "drift", label: `Workspace drift · ${m.drift}` });
  if (notes > 0) out.push({ id: "notes", label: `Stage notes · ${notes}` });
  if (m.ai) out.push({ id: "ai", label: `AI calls used · ${m.ai.used} of ${m.ai.budget}` });
  if (m.reading) out.push({ id: "help", label: "How to read this page" });
  if (m.owner && m.ready) out.push({ id: "rerun", label: "Re-run" });
  if (m.owner && m.ready && m.strong) out.push({ id: "fresh", label: "Re-run stories, fresh" });
  return out;
}

/** What the amber dot on ⋯ is for, said in the button's name; null when nothing needs attention (a degraded stage
 * alone does not light it). */
export function menuAttention(m: MenuState): string | null {
  const why: string[] = [];
  if (m.drift > 0) why.push("workspace drift");
  if (m.notes.failed > 0) why.push("a stage failed");
  return why.length ? why.join(", ") : null;
}
```

- [ ] **Step 4: Run the unit tests**

Run: `cd frontend && npx vitest run src/reading/causes.test.ts src/lib/aiState.test.ts src/workspace/reviewMenu.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit the rules**

```bash
git add frontend/src/reading/causes.ts frontend/src/reading/causes.test.ts frontend/src/lib/aiState.ts frontend/src/lib/aiState.test.ts frontend/src/workspace/reviewMenu.ts frontend/src/workspace/reviewMenu.test.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(header): the review menu's items and dot, the AI pill's 90% rule, checks in the progress line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

- [ ] **Step 6: Write the failing e2e tests**

In `frontend/e2e/helpers.ts`, add at the end:

```ts
/** Open the header's ⋯ menu (spec 2026-10-25-review-ui-redesign §2.2) unless it is open; returns the menu. */
export async function reviewMenu(page: Page): Promise<Locator> {
  const menu = page.getByRole("menu", { name: "Review menu" });
  if (!(await menu.isVisible())) await page.getByRole("button", { name: /^Review menu/ }).click();
  await expect(menu).toBeVisible();
  return menu;
}

/** Open the AI usage panel from the review menu; returns the panel. */
export async function openAiUsage(page: Page): Promise<Locator> {
  await (await reviewMenu(page)).getByRole("menuitem", { name: /^AI calls used · / }).click();
  const usage = page.getByRole("dialog", { name: "AI usage" });
  await expect(usage).toBeVisible();
  return usage;
}
```

Create `frontend/e2e/header-menu.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { reviewMenu, startReview } from "./helpers";

/** The header's one row and its ⋯ menu (spec 2026-10-25-review-ui-redesign §2). */
test.use({ viewport: { width: 1440, height: 900 } });

test("the header keeps one quiet row; the rest is in the review menu, which the keyboard walks", async ({ page }) => {
  await startReview(page);
  const head = page.locator(".ws-head");
  await expect(head.locator(".ct-headline")).toHaveText("Medium risk");
  await expect(head.getByRole("button", { name: "Re-run" })).toHaveCount(0);
  await expect(head.getByRole("button", { name: "How to read this page" })).toHaveCount(0);
  await expect(head.locator(".bd-notes")).toHaveCount(0);
  const button = page.getByRole("button", { name: "Review menu" });           // the demo: no drift, no failed stage
  await expect(button.locator(".rm-dot")).toHaveCount(0);
  const menu = await reviewMenu(page);
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(menu.getByRole("menuitem")).toHaveText([/^Stage notes · \d+$/, "How to read this page", "Re-run"]);
  await expect(menu.getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(menu.getByRole("menuitem", { name: "How to read this page" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(button).toBeFocused();
  await (await reviewMenu(page)).getByRole("menuitem", { name: /^Stage notes/ }).click();
  const notes = page.getByRole("dialog", { name: "Stage notes" });
  await expect(notes).toContainText("swarm_read");
  await page.getByRole("region", { name: "Centre" }).click({ position: { x: 5, y: 5 } });   // a press outside closes it
  await expect(notes).toHaveCount(0);
});

test("a drifted workspace or a failed stage lights a dot on the menu and says why in its name", async ({ page }) => {
  const base = await startReview(page);
  await page.route("**/api/reviews/*/board", async (route) => {
    const res = await route.fetch(), j = await res.json();
    j.about.drift = [{ text: "//fixture/driver/uart.c (base #3, workspace #2)", kind: "behind", severity: "warn" }];
    await route.fulfill({ response: res, json: j });
  });
  await page.route(/\/api\/reviews\/\d+$/, async (route) => {
    const res = await route.fetch(), j = await res.json();
    j.stages = j.stages.map((s: { name: string }) => (s.name === "swarm_read" ? { ...s, status: "failed", message: "Swarm is down" } : s));
    await route.fulfill({ response: res, json: j });
  });
  await page.goto(base);
  const button = page.getByRole("button", { name: "Review menu (workspace drift, a stage failed)" });
  await expect(button.locator(".rm-dot")).toBeVisible();
  const menu = await reviewMenu(page);
  await menu.getByRole("menuitem", { name: "Workspace drift · 1" }).click();
  const drift = page.getByRole("dialog", { name: "Workspace drift" });
  await expect(drift).toContainText("//fixture/driver/uart.c (base #3, workspace #2)");
  await page.keyboard.press("Escape");
  await expect(drift).toHaveCount(0);
  await expect(button).toBeFocused();
});
```

In `frontend/e2e/ai.spec.ts`, change the import line to

```ts
import { explainItem, login, openAiUsage, openIndex, startReview } from "./helpers";
```

and replace the whole test `"the owner raises the budget from the AI pill; a reviewer sees the usage without the control"` with:

```ts
  test("the owner raises the budget from the review menu; a reviewer sees the usage without the control", async ({ page, browser }) => {
    await startReview(page);
    await expect(page.getByRole("button", { name: /^AI \d+\/200$/ })).toHaveCount(0);   // far from the limit: no pill
    const usage = await openAiUsage(page);
    await expect(usage).toContainText("By purpose: story_account 2 · finding 1 · flow 1 · summary 1 · verdict 1");
    await usage.getByText(/^All calls/).click();                          // the call list loads when opened
    await expect(usage.locator(".ai-calls tbody tr")).toHaveCount(6);                // + an account per behaviour story
    await usage.getByLabel("New budget").fill("300");
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(usage).toContainText(/This review: \d+ of 300\./);
    await expect(usage.getByLabel("Rounds per @tortoise answer")).toHaveValue("10");
    await usage.getByLabel("Rounds per @tortoise answer").fill("4");
    await usage.getByRole("button", { name: "Set rounds" }).click();
    await expect(usage).toContainText("One @tortoise answer is 1 AI call of up to 4 rounds.");

    const bob = await browser.newPage({ baseURL: AI });
    await login(bob, "bob");
    await bob.goto(page.url());
    const theirs = await openAiUsage(bob);
    await expect(theirs).toContainText("You today: 0 of 100");
    await expect(theirs.getByRole("button", { name: "Raise budget" })).toHaveCount(0);
    await expect(theirs).toContainText("One @tortoise answer is 1 AI call of up to 4 rounds.");
    await expect(theirs.getByRole("button", { name: "Set rounds" })).toHaveCount(0);
    await bob.close();
  });
```

In `frontend/e2e/mention.spec.ts`, change the import line to

```ts
import { contrast, explainItem, openAiUsage, openIndex, reviewMenu, startReview } from "./helpers";
```

replace

```ts
    await startReview(page);
    await page.getByRole("button", { name: /^AI \d+\/200$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await usage.getByLabel("New budget").fill("6");          // the run used 6: verdicts, summary, 1 flow, 1 finding, 2 story accounts
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("button", { name: "AI 6/6" })).toBeVisible();
```

with

```ts
    await startReview(page);
    const usage = await openAiUsage(page);
    await usage.getByLabel("New budget").fill("6");          // the run used 6: verdicts, summary, 1 flow, 1 finding, 2 story accounts
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("button", { name: "AI 6/6" })).toBeVisible();          // at the limit the pill comes back
    expect(await contrast(page, ".ws-head .ai-pill")).toBeGreaterThanOrEqual(4.5);   // readable on the light head
```

and in `"without an AI"`, replace

```ts
    await expect(page.getByRole("button", { name: /^AI \d+/ })).toHaveCount(0);
```

with

```ts
    await expect(page.getByRole("button", { name: /^AI \d+/ })).toHaveCount(0);
    await expect((await reviewMenu(page)).getByRole("menuitem", { name: /^AI calls used/ })).toHaveCount(0);
    await page.keyboard.press("Escape");
```

In `frontend/e2e/workspace-tier1.spec.ts`, change the import line to

```ts
import { expectNamed, login, openAiUsage, reviewMenu, startReview } from "./helpers";
```

replace

```ts
    await page.getByRole("button", { name: /^AI \d+\/\d+$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await expect(usage).toContainText(/Strong model \(fake-strong\): \d+ of 40 calls/);
    await usage.getByRole("button", { name: "Close" }).click();
    await page.getByRole("button", { name: "Re-run stories (fresh)" }).click();
```

with

```ts
    const usage = await openAiUsage(page);
    await expect(usage).toContainText(/Strong model \(fake-strong\): \d+ of 40 calls/);
    await usage.getByRole("button", { name: "Close" }).click();
    const fresh = (await reviewMenu(page)).getByRole("menuitem", { name: "Re-run stories, fresh" });
    await expect(fresh).toHaveAttribute("title", "Ask the strong model for new stories instead of reusing the ones it formed for this change");
    await fresh.click();
```

and replace

```ts
    await page.getByRole("button", { name: /^AI \d+\/\d+$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await usage.getByText(/^All calls/).click();
```

with

```ts
    const usage = await openAiUsage(page);
    await usage.getByText(/^All calls/).click();
```

In `frontend/e2e/workspace-story.spec.ts`, change the import line to

```ts
import { expectNamed, expectNoNodeIds, flowStripHolds, openIndex, reviewMenu, startReview } from "./helpers";
```

and replace

```ts
    await page.getByRole("button", { name: "Re-run" }).click();
```

with

```ts
    await (await reviewMenu(page)).getByRole("menuitem", { name: "Re-run", exact: true }).click();
```

In `frontend/e2e/outline-causes.spec.ts`, change the import line to

```ts
import { expectNamed, expectNoNodeIds, hold, reviewMenu, startReview } from "./helpers";
```

replace `"0 of 5 stories read · 4 causes open"` with `"0 of 5 stories read · 4 checks open"` and `"0 of 5 stories read · 3 causes open"` with `"0 of 5 stories read · 3 checks open"`, and replace the whole test `"? opens how to read the page; Escape closes it"` with:

```ts
  test("the review menu opens how to read the page; Escape closes it and returns to the menu", async ({ page }) => {
    await startReview(page, FOUR);
    await (await reviewMenu(page)).getByRole("menuitem", { name: "How to read this page" }).click();
    const dialog = page.getByRole("dialog", { name: "How to read this page" });
    await expect(dialog).toContainText("J next, K back, F looks fine & next");
    await expect(dialog).toContainText("A faint violet line at the left of a paragraph marks text the AI wrote.");
    for (const w of [1440, 600]) {
      await page.setViewportSize({ width: w, height: 900 });
      await expect(dialog).toBeVisible();
      const seen = await dialog.evaluate((el) => {
        const b = el.getBoundingClientRect();
        const top = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
        return { inside: b.left >= 0 && b.top >= 0 && b.right <= window.innerWidth && b.bottom <= window.innerHeight,
                 hit: !!top && el.contains(top) };
      });
      expect(seen).toEqual({ inside: true, hit: true });
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Review menu/ })).toBeFocused();
  });
```

In `frontend/e2e/workspace-reading.spec.ts`, replace `"0 of 5 stories read · 3 causes open"` with `"0 of 5 stories read · 3 checks open"`, and

```ts
    await expect(outline.getByRole("link", { name: "Go to the overview" })).toContainText("Medium risk · rules only");
```

with

```ts
    await expect(outline.getByRole("link", { name: "Go to the overview" })).toContainText("Medium risk");
```

In `frontend/e2e/workspace-plan.spec.ts`, replace

```ts
    const line = (k: number) => new RegExp(`^${k} of ${order.length} stories read( · (\\d+ causes? open|every check done))?$`);
```

with

```ts
    const line = (k: number) => new RegExp(`^${k} of ${order.length} stories read( · (\\d+ checks? open|every check done))?$`);
```

In `frontend/e2e/workspace.spec.ts`, replace

```ts
    await expect(head.locator(".ct-headline")).toHaveText("Medium risk · rules only");   // header fan-out never raises it
```

with

```ts
    await expect(head.locator(".ct-headline")).toHaveText("Medium risk");                // header fan-out never raises it
    await expect(head.locator(".ct-headline")).toHaveAttribute("title", "Judged by the detectors' rules, without the strong model");
```

In `frontend/e2e/landing.spec.ts`, replace

```ts
    for (const r of await rows.all()) await expect(r.locator(".rv-headline")).toHaveText(/ risk · rules only$/);
```

with

```ts
    for (const r of await rows.all()) {
      await expect(r.locator(".rv-headline")).toHaveText(/ risk$/);
      await expect(r.locator(".rv-headline")).toHaveAttribute("title", "Judged by the detectors' rules, without the strong model");
    }
```

- [ ] **Step 7: Build and run the header specs to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/header-menu.spec.ts e2e/outline-causes.spec.ts -g "review menu|header|walks the open causes"`
Expected: FAIL — no button named `Review menu`; the progress line still says "causes open"; the pill still reads "Medium risk · rules only".

- [ ] **Step 8: Build the header row, the menu and its panels**

Replace `frontend/src/components/HeadlinePill.tsx` with:

```tsx
import type { Headline } from "../reading/types";

/** What to act on (spec 2026-10-07-review-reading §5.4): red for open hazards, amber for checks to confirm, neutral
 * otherwise; when the strong model did not judge the risks, the hover says so (spec 2026-10-25-review-ui-redesign §2.1). */
export default function HeadlinePill({ h, className = "" }: { h: Headline; className?: string }) {
  return (
    <span className={`ct-headline ${h.tone} ${className}`.trim()}
          title={h.rules_only ? "Judged by the detectors' rules, without the strong model" : undefined}>
      {h.text}
    </span>
  );
}
```

In `frontend/src/components/AiPill.tsx`:

Change the imports to

```tsx
import { useEffect, useRef, useState } from "react";
import { api, type AiCall } from "../api";
import { useAi } from "../lib/ai";
import { nearLimit } from "../lib/aiState";
import { hasRequests, requestLogHref } from "./requestLog";
```

Replace the `AiPill` function with:

```tsx
/** The review header's AI pill, shown only near the review's budget (spec 2026-10-25-review-ui-redesign §2.1); it
 * opens the usage panel, as the ⋯ menu's "AI calls used" does. */
export default function AiPill() {
  const ai = useAi();
  const v = ai?.view;
  if (!ai || !v || !nearLimit(v)) return null;
  return (
    <button className="bd-pill ai-pill high" aria-expanded={ai.usageOpen} title="AI calls used on this review"
            onClick={() => ai.setUsageOpen(!ai.usageOpen)}>AI {v.used}/{v.budget}</button>
  );
}
```

Replace the start of `Usage`, from

```tsx
function Usage({ onClose }: { onClose: () => void }) {
  const ai = useAi()!;
  const v = ai.view!;
```

to

```tsx
/** The AI usage panel (spec 2026-10-03 §6): this review's and the viewer's calls; the owner raises the budget. It sits
 * under the header's right end at `top`, whoever opened it (spec 2026-10-25-review-ui-redesign §2.2). */
export function Usage({ onClose, top }: { onClose: () => void; top: number }) {
  const ai = useAi()!;
  const v = ai.view!;
  const box = useRef<HTMLDivElement>(null);
```

replace its effect

```tsx
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
```

with

```tsx
  useEffect(() => {                           // Escape or a press outside closes it; the pill toggles it itself
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const away = (e: PointerEvent) => {
      const t = e.target as Element;
      if (!box.current?.contains(t) && !t.closest?.(".ai-pill")) onClose();
    };
    window.addEventListener("keydown", esc);
    document.addEventListener("pointerdown", away);
    return () => { window.removeEventListener("keydown", esc); document.removeEventListener("pointerdown", away); };
  }, [onClose]);
```

and replace

```tsx
    <div className="ai-usage" role="dialog" aria-label="AI usage">
```

with

```tsx
    <div className="ai-usage" role="dialog" aria-label="AI usage" ref={box} style={{ top }}>
```

Replace `frontend/src/workspace/HowToRead.tsx` with:

```tsx
/** How to read a review (spec 2026-10-16-outline-and-causes §1.1), for a reader new to CodeTortoise: a panel the
 * header's ⋯ menu opens at `top` (spec 2026-10-25-review-ui-redesign §2.2); the menu closes it. */
export default function HowToRead({ top }: { top: number }) {
  return (
    <div className="ws-help-pop rm-panel" role="dialog" aria-label="How to read this page" tabIndex={-1} style={{ top }}>
      <h2>How to read this page</h2>
      <ul>
        <li><b>The outline</b> on the left lists the change's threads — stories joined by calls or shared data, lettered
          A, B… — and each thread's stories in reading order; the story you are on shows its flows.</li>
        <li><b>Checks</b> at the top of the outline lists what needs a reviewer's eye, grouped by the change that raised
          it. <b>Showing</b> hides kinds of check; Confirm is hidden until you show it.</li>
        <li><b>A check</b> opens beside the page: the change that raised it above each place it asks you to look at.
          <b> Looks fine &amp; next</b> clears a place for everyone, <b>All look fine</b> clears them all, <b>Comment</b>
          starts a thread. Keys: J next, K back, F looks fine &amp; next.</li>
        <li><b>Next open check ›</b> goes to the next place still open, in reading order.</li>
        <li><b>A story</b> has tabs: Flows (each path through the change, with its checks), Before → after, Where, Call
          paths, Code, Graph and Talk.</li>
        <li><b>Mark as read</b> ticks a story for you alone; the top bar counts the stories you have read and the checks
          still open.</li>
        <li><b>The side panel</b> keeps a tab per thing you open; <b>Focus</b> folds the outline to give it room.</li>
        <li>A faint violet line at the left of a paragraph marks text the AI wrote.</li>
      </ul>
    </div>
  );
}
```

Create `frontend/src/workspace/ReviewMenu.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useMe } from "../App";
import { driftSummary } from "../board/drift";
import { useAi } from "../lib/ai";
import { useMenu } from "../lib/useMenu";
import { useWs } from "./context";
import HowToRead from "./HowToRead";
import { menuAttention, type MenuId, menuItems, type MenuState } from "./reviewMenu";

const FRESH = "Ask the strong model for new stories instead of reusing the ones it formed for this change";

/** The header's ⋯ menu (spec 2026-10-25-review-ui-redesign §2.2): drift, stage notes, AI usage, the help and the
 * owner's re-runs, with an amber dot when the workspace drifted or a stage failed. The menu and its panels are fixed
 * under the header's right end (`under()`), since the header itself scrolls. */
export default function ReviewMenu({ under }: { under: () => number }) {
  const ws = useWs(), d = ws.data, me = useMe(), ai = useAi();
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"drift" | "notes" | "help" | null>(null);
  const [top, setTop] = useState(56);
  const { button, menu } = useMenu<HTMLUListElement>(open, () => setOpen(false));
  const box = useRef<HTMLDivElement>(null);
  const drift = driftSummary(d.about?.drift ?? []).warn;
  const notes = d.detail!.stages.filter((s) => s.status === "failed" || s.status === "degraded");
  const v = ai?.view;
  const state: MenuState = {
    drift: drift.length, notes: { failed: notes.filter((s) => s.status === "failed").length,
                                  degraded: notes.filter((s) => s.status === "degraded").length },
    ai: v?.llm ? { used: v.used, budget: v.budget } : null, reading: !!d.reading,
    owner: !!me?.is_owner, ready: d.ready, strong: !!v?.strong };
  const items = menuItems(state), why = menuAttention(state);
  useEffect(() => {                           // a panel takes focus; Escape (back to ⋯) or a press outside closes it
    if (!panel) return;
    box.current?.querySelector<HTMLElement>('[role="dialog"]')?.focus();
    const place = () => setTop(under());
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setPanel(null); button.current?.focus(); } };
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!box.current?.contains(t) && !button.current?.contains(t)) setPanel(null);
    };
    window.addEventListener("resize", place);
    document.addEventListener("keydown", esc);
    document.addEventListener("pointerdown", away);
    return () => { window.removeEventListener("resize", place); document.removeEventListener("keydown", esc);
                   document.removeEventListener("pointerdown", away); };
  }, [panel, under, button]);
  if (!items.length) return null;
  const pick = (id: MenuId) => {
    setOpen(false);
    if (id === "drift" || id === "notes" || id === "help") { setPanel(id); return; }
    button.current?.focus();
    if (id === "ai") ai?.setUsageOpen(true);
    else api.rerun(d.id, id === "fresh").then(d.loadDetail);
  };
  return (
    <div className="rm">
      <button ref={button} className="rm-btn" aria-label={why ? `Review menu (${why})` : "Review menu"} title="Review menu"
              aria-haspopup="menu" aria-expanded={open}
              onClick={() => { setTop(under()); setPanel(null); setOpen(!open); }}>
        ⋯{why && <span className="rm-dot" aria-hidden />}
      </button>
      {open && (
        <ul className="rm-menu" role="menu" aria-label="Review menu" ref={menu} style={{ top }}>
          {items.map((it) => (
            <li key={it.id} role="none">
              <button role="menuitem" title={it.id === "fresh" ? FRESH : undefined} onClick={() => pick(it.id)}>
                {(it.id === "drift" || (it.id === "notes" && state.notes.failed > 0)) && <span className="rm-amber" aria-hidden />}
                {it.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div ref={box}>
        {panel === "drift" && (
          <div className="rm-panel" role="dialog" aria-label="Workspace drift" tabIndex={-1} style={{ top }}>
            <h2>Workspace drift</h2>
            <p className="muted small">The workspace differs from the change in these files; what the review says about them may be off.</p>
            <ul className="mono small">{drift.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
        )}
        {panel === "notes" && (
          <div className="rm-panel" role="dialog" aria-label="Stage notes" tabIndex={-1} style={{ top }}>
            <h2>Stage notes</h2>
            {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>)}
          </div>
        )}
        {panel === "help" && <HowToRead top={top} />}
      </div>
    </div>
  );
}
```

(`api.rerun(id, fresh = false)` in `src/api.ts` adds `?fresh=true` only when `fresh` is true, so a plain Re-run passes `false`.)

In `frontend/src/workspace/Workspace.tsx`:

Replace

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
```

with

```tsx
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
```

delete

```tsx
import { useMe } from "../App";
import { driftSummary } from "../board/drift";
```

replace

```tsx
import AiPill from "../components/AiPill";
```

with

```tsx
import AiPill, { Usage } from "../components/AiPill";
```

delete

```tsx
import HowToRead from "./HowToRead";
```

and after `import Rail from "./Rail";` add

```tsx
import ReviewMenu from "./ReviewMenu";
```

Replace the start of `Head`, from

```tsx
function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
  const ws = useWs(), me = useMe(), ai = useAi(), d = ws.data, r = d.detail!.review;
  const notes = d.detail!.stages.filter((s) => s.status === "failed" || s.status === "degraded");
  const drift = driftSummary(d.about?.drift ?? []).warn;
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(loadHeadH);          // null: as tall as its content
```

to

```tsx
function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
  const ws = useWs(), ai = useAi(), d = ws.data, r = d.detail!.review;
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(loadHeadH);          // null: as tall as its content
  const under = useCallback(() => (box.current?.getBoundingClientRect().bottom ?? 50) + 6, []);
  const [usageTop, setUsageTop] = useState(56);
  useLayoutEffect(() => {                                   // the usage panel sits under the header, whoever opened it
    if (!ai?.usageOpen) return;
    const place = () => setUsageTop(under());
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [ai?.usageOpen, under]);
```

and replace the end of the header row and the box, from

```tsx
        {rd && <HowToRead />}
        {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
        {d.ready && <AiPill />}
        {me?.is_owner && d.ready && <button className="link rerun" onClick={() => api.rerun(d.id).then(d.loadDetail)}>Re-run</button>}
        {me?.is_owner && d.ready && ai?.view?.strong && (
          <button className="link" title="Ask the strong model for new stories instead of reusing the ones it formed for this change"
                  onClick={() => api.rerun(d.id, true).then(d.loadDetail)}>Re-run stories (fresh)</button>
        )}
        {drift.length > 0 && <span className="bd-pill high" title={drift.join("\n")}>⚠ workspace drift ({drift.length})</span>}
        {notes.length > 0 && (
          <details className="bd-notes">
            <summary>{notes.length} stage note(s)</summary>
            {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>)}
          </details>
        )}
      </header>
```

to

```tsx
        {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
        {d.ready && <AiPill />}
        <ReviewMenu under={under} />
      </header>
      {ai?.usageOpen && ai.view?.llm && <Usage top={usageTop} onClose={() => ai.setUsageOpen(false)} />}
```

In `frontend/src/styles.css`, delete

```css
.ai-pillwrap { position: relative; display: inline-flex; }
```

and

```css
.ct-headline .ct-rules { font-weight: 400; }
```

In `frontend/src/workspace/workspace.css`, delete

```css
.ws-head .rerun { margin-left: auto; }
```

and after the line `.ws-help-pop li + li { margin-top: 6px; }` add:

```css
/* the header's ⋯ menu and its panels (spec 2026-10-25-review-ui-redesign §2.2) */
.rm { margin-left: auto; display: inline-flex; }
.rm-btn { position: relative; font-size: 15px; line-height: 1; padding: 4px 11px; }
.rm-dot { position: absolute; top: -3px; right: -3px; width: 9px; height: 9px; border-radius: 50%; background: var(--warn);
  border: 2px solid var(--surface); }
.rm-menu { position: fixed; right: 16px; z-index: 60; min-width: 250px; margin: 0; padding: 4px 0; list-style: none;
  background: var(--surface); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 6px 18px rgb(0 0 0 / .14); }
.rm-menu [role="menuitem"] { display: flex; align-items: center; gap: 8px; width: 100%; border: 0; border-radius: 0;
  background: none; padding: 6px 14px; text-align: left; white-space: nowrap; }
.rm-menu [role="menuitem"]:hover, .rm-menu [role="menuitem"]:focus-visible { background: var(--gap-bg); }
.rm-amber { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--warn); }
.rm-panel { position: fixed; right: 16px; z-index: 60; width: min(440px, calc(100vw - 32px)); max-height: calc(100vh - 80px);
  overflow-y: auto; padding: 12px 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 8px;
  box-shadow: 0 6px 24px rgb(0 0 0 / .18); font-size: 13.5px; line-height: 1.45; }
.rm-panel h2 { margin: 0 0 6px; font-size: 15px; }
.rm-panel ul { margin: 0; padding-left: 18px; }
.rm-panel:focus { outline: none; }
```

- [ ] **Step 9: Check, build and run the header specs**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && E2E e2e/header-menu.spec.ts e2e/outline-causes.spec.ts e2e/ai.spec.ts e2e/mention.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-story.spec.ts e2e/workspace-reading.spec.ts e2e/workspace-plan.spec.ts e2e/workspace.spec.ts e2e/landing.spec.ts`
Expected: every unit test and every listed spec PASS; `tsc` prints nothing.

- [ ] **Step 10: Commit the header**

```bash
git add frontend/src frontend/e2e
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(header): one quiet row; drift, stage notes, AI usage, help and re-runs move into a ⋯ menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

- [ ] **Step 11: Phase 1 gate — the whole suite**

Run: `cd backend && env PYTHONPATH=$PWD .venv/bin/python -m pytest -q -p no:cacheprovider tests && cd ../frontend && npx vitest run && npm run build && E2E 2>&1 | tail -40; rm -rf $(git rev-parse --show-toplevel)/.pwtmp`
Expected: pytest, vitest and every e2e spec PASS. A failure in a spec this phase did not touch is investigated (superpowers:systematic-debugging), not skipped.

- [ ] **Step 12: Phase 1 screenshots for the owner**

Create the scratch spec `frontend/e2e/zz-shots.spec.ts` (never committed):

```ts
import { test } from "@playwright/test";
import { startReview } from "./helpers";

const OUT = "../.superpowers/screens/phase-1";

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test("phase 1", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page, "101 102 103 104");
    await page.screenshot({ path: `${OUT}/overview.png` });
    await page.getByRole("button", { name: /^Review menu/ }).click();
    await page.screenshot({ path: `${OUT}/menu.png` });
    await page.keyboard.press("Escape");
    await page.goto(`${base}/f/F4?details=1`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/finding.png` });
  });
});

test.describe("with an AI", () => {
  test.use({ baseURL: "http://127.0.0.1:8798", viewport: { width: 1440, height: 900 } });
  test("phase 1 AI", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await page.locator(".st-summary .ai-text").waitFor({ timeout: 30_000 });
    await page.screenshot({ path: `${OUT}/story-ai.png` });
    await page.getByRole("button", { name: "Explain", exact: true }).first().click();
    await page.screenshot({ path: `${OUT}/explain-menu.png` });
  });
});

test.describe("phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("phase 1 phone", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page, "101 102 103 104");
    await page.goto(`${base}/s/S1`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/story-phone.png` });
  });
});
```

Run: `cd frontend && E2E e2e/zz-shots.spec.ts; rm e2e/zz-shots.spec.ts; rm -rf $(git rev-parse --show-toplevel)/.pwtmp; ls ../.superpowers/screens/phase-1 && git status --short`
Expected: six PNGs listed; `git status` shows no file this step made. Send the PNGs to the owner (SendUserFile, when the session has it) with one line: "Phase 1: chips gone, faint AI edge, dark headings, one header row with ⋯."

## Phase 2 — overview and outline (spec §5–§6)

### Task 7: The overview's rules: heading, start button, a thread's counts and action, its connections, the folded rows

**Files:**
- Modify: `frontend/src/reading/overview.ts` (new functions; `connectionRows` stays until Task 8 removes its only user)
- Test: `frontend/src/reading/overview.test.ts`

**Interfaces:**
- Consumes: `letter(i, id)` (`reading/checks.ts`); `shown`, `causeOpen` (`reading/causes.ts`); `Reading`, `Thread`, `Connection`, `Cause`, `CheckKind`, `Mark` (`reading/types.ts`).
- Produces (all exported from `src/reading/overview.ts`):
  - `overviewHeading(n: number): string` — `"The change"` (0), `"1 thread"`, `"<n> threads"`.
  - `startButton(r: Pick<Reading, "order" | "threads">, read: ReadonlySet<string>): { sid: string; label: string } | null` — the first unread story in reading order; label `"Continue ›"` once any story is read, else `"Start with Thread <L> ›"` (`"Start here ›"` when that story is in no thread); `null` when every story is read or there are none.
  - `type ThreadAction = { kind: "start" | "continue"; sid: string } | { kind: "done" }`; `threadAction(stories: string[], read: ReadonlySet<string>): ThreadAction | null` — `null` for a thread with no stories.
  - `threadCounts(t: Thread, causes: Cause[] | null | undefined, hidden: ReadonlySet<CheckKind>, marks: Record<string, Mark>, read: ReadonlySet<string>): { stories: number; open: number | null; read: number }` — `open` is `null` on a reading without causes.
  - `sectionConnections(threads: Thread[], conns: Connection[]): Map<string, { text: string; bundled: boolean }[]>` — keyed by the later thread's id; text `"With Thread <L>: <text>"`, plus `" — ask the author"` when bundled; shown connections between two known, different threads only.
  - `foldTitles(r: Pick<Reading, "build_impact" | "coverage" | "rules_only" | "sinks">, comments: { parent_id: number | null; anchor_kind: string }[]): { build: string | null; coverage: string | null; discussion: string }`.
  - `listed`, `testsLine`, `cardText` stay as they are; `connectionRows` is deleted in Task 8.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/reading/overview.test.ts`, replace the head of the file — from

```ts
import { describe, expect, it } from "vitest";
import { cardText, connectionRows, testsLine } from "./overview";
import type { Connection, TestsRow, Thread } from "./types";

const thread = (id: string, name = id): Thread => ({ id, name, purpose: "", text_source: "template", stories: [], cls: [], open_checks: 0 });
```

— with (the `conn` and `T` lines after it stay):

```ts
import { describe, expect, it } from "vitest";
import { cardText, connectionRows, foldTitles, overviewHeading, sectionConnections, startButton, testsLine, threadAction,
  threadCounts } from "./overview";
import type { BuildImpact, Cause, Connection, Mark, SinkHit, TestsRow, Thread } from "./types";

const thread = (id: string, name = id, stories: string[] = []): Thread =>
  ({ id, name, purpose: "", text_source: "template", stories, cls: [], open_checks: 0 });
```

Then, directly after the line `const T = ["T1", "T2", "T3", "T4"].map((id) => thread(id));`, add:

```ts

describe("the overview's heading and start button (spec 2026-10-25-review-ui-redesign §5.1)", () => {
  it("counts the threads, and says the change when there are none", () => {
    expect(overviewHeading(0)).toBe("The change");
    expect(overviewHeading(1)).toBe("1 thread");
    expect(overviewHeading(5)).toBe("5 threads");
  });

  const r = { order: ["S2", "S1", "S3", "S9"], threads: [thread("T1", "a", ["S2", "S1"]), thread("T2", "b", ["S3"])] };

  it("names the thread of the first story in reading order before anything is read", () => {
    expect(startButton(r, new Set())).toEqual({ sid: "S2", label: "Start with Thread A ›" });
    expect(startButton({ ...r, order: ["S3", "S2", "S1", "S9"] }, new Set())).toEqual({ sid: "S3", label: "Start with Thread B ›" });
  });

  it("says Start here when the first story is in no thread, or there are no threads", () => {
    expect(startButton({ order: ["S9", "S2"], threads: r.threads }, new Set())).toEqual({ sid: "S9", label: "Start here ›" });
    expect(startButton({ order: ["S1"], threads: [] }, new Set())).toEqual({ sid: "S1", label: "Start here ›" });
  });

  it("continues at the first unread story once one is read, whichever it was", () => {
    expect(startButton(r, new Set(["S2"]))).toEqual({ sid: "S1", label: "Continue ›" });
    expect(startButton(r, new Set(["S1"]))).toEqual({ sid: "S2", label: "Continue ›" });
  });

  it("has no button when every story is read or there are none", () => {
    expect(startButton(r, new Set(["S2", "S1", "S3", "S9"]))).toBeNull();
    expect(startButton({ order: [], threads: [] }, new Set())).toBeNull();
  });
});

describe("a thread section's action and counts (§5.2)", () => {
  it("starts at the first story, continues at the first unread one, and is done when all are read", () => {
    expect(threadAction(["S2", "S1"], new Set())).toEqual({ kind: "start", sid: "S2" });
    expect(threadAction(["S2", "S1"], new Set(["S2"]))).toEqual({ kind: "continue", sid: "S1" });
    expect(threadAction(["S2", "S1"], new Set(["S1"]))).toEqual({ kind: "continue", sid: "S2" });
    expect(threadAction(["S2", "S1"], new Set(["S1", "S2"]))).toEqual({ kind: "done" });
    expect(threadAction([], new Set())).toBeNull();
  });

  const cause = (id: string, threadId: string | null, kind: Cause["kind"], places: string[]): Cause =>
    ({ id, kind, thread: threadId, story: null, text: id, places, flows: [], finding: null, change: null });
  const mark = (key: string, changed = false): Mark => ({ key, user: "ann", at: "2026-10-25T09:00:00Z", source_line: "", changed });
  const t = thread("T1", "a", ["S1", "S2", "S3"]);

  it("counts the thread's shown causes still open and the stories the reader has read", () => {
    const causes = [cause("c1", "T1", "caller", ["k1"]), cause("c2", "T1", "reader", ["k2", "k3"]),
                    cause("c3", "T1", "confirm", ["k4"]), cause("c4", "T2", "caller", ["k5"]), cause("c5", "T1", "result", ["k6"])];
    const marks = { k1: mark("k1"), k2: mark("k2"), k6: mark("k6", true) };
    // c1 is marked; c2 still has k3; c3's kind is hidden; c4 is another thread's; c5's line changed since its mark
    expect(threadCounts(t, causes, new Set(["confirm"]), marks, new Set(["S2", "S9"]))).toEqual({ stories: 3, open: 2, read: 1 });
  });

  it("has no open count on a reading stored before causes", () => {
    expect(threadCounts(t, null, new Set(), {}, new Set())).toEqual({ stories: 3, open: null, read: 0 });
    expect(threadCounts(t, undefined, new Set(), {}, new Set())).toEqual({ stories: 3, open: null, read: 0 });
  });
});

describe("how the threads connect, under the later thread (§5.2)", () => {
  it("puts each shown connection under the later of its two threads, naming the earlier one", () => {
    const rows = sectionConnections(T, [conn("T1", "T2", "caller", true, "both run inside `main`"),
                                        conn("T4", "T2", "bundled", true, "nothing besides arriving in CL 104"),
                                        conn("T1", "T3", "place", false),
                                        conn("T3", "T1", "vocabulary", true, "both use `hal_write`"),
                                        conn("T1", "T9", "caller", true, "a thread the reading no longer has")]);
    expect([...rows.entries()]).toEqual([
      ["T2", [{ text: "With Thread A: both run inside `main`", bundled: false }]],
      ["T4", [{ text: "With Thread B: nothing besides arriving in CL 104 — ask the author", bundled: true }]],
      ["T3", [{ text: "With Thread A: both use `hal_write`", bundled: false }]],
    ]);
  });

  it("has nothing to show for one thread or none", () => {
    expect(sectionConnections([thread("T1")], [conn("T1", "T1")]).size).toBe(0);
    expect(sectionConnections([], [conn("T1", "T2")]).size).toBe(0);
  });
});

describe("the folded rows after the threads (§5.3)", () => {
  const bi = (files: number): BuildImpact => ({ header: "uart.h", text: "", files, finding: null, note: "" });
  const sink: SinkHit = { field: "N7", label: "Stats::tx", users: 9, why: "listed", writers: [] };
  const none = { build_impact: [] as BuildImpact[], coverage: [] as string[], rules_only: false };

  it("leaves out Build impact and Coverage when they have nothing, and keeps Discussion", () => {
    expect(foldTitles(none, [])).toEqual({ build: null, coverage: null, discussion: "Discussion · no comments yet" });
  });

  it("says the most files a change rebuilds", () => {
    expect(foldTitles({ ...none, build_impact: [bi(3), bi(4)] }, []).build).toBe("Build impact · up to 4 files rebuild");
    expect(foldTitles({ ...none, build_impact: [bi(1)] }, []).build).toBe("Build impact · up to 1 file rebuilds");
    expect(foldTitles({ ...none, build_impact: [bi(0)] }, []).build).toBe("Build impact");
  });

  it("counts coverage lines, plus one for rules only and one for shared sinks", () => {
    expect(foldTitles({ ...none, coverage: ["No test code found in the workspace"], rules_only: true }, []).coverage)
      .toBe("Coverage · 2 notes");
    expect(foldTitles({ ...none, coverage: ["No test code found in the workspace"] }, []).coverage).toBe("Coverage · 1 note");
    expect(foldTitles({ ...none, sinks: [sink, sink] }, []).coverage).toBe("Coverage · 1 note");
  });

  it("counts top-level review and layer comments only", () => {
    const c = (parent_id: number | null, anchor_kind: string) => ({ parent_id, anchor_kind });
    expect(foldTitles(none, [c(null, "review"), c(null, "chapter"), c(1, "review"), c(null, "function"), c(null, "story")]).discussion)
      .toBe("Discussion · 2 comments");
    expect(foldTitles(none, [c(null, "review")]).discussion).toBe("Discussion · 1 comment");
  });
});
```

(The existing `describe` blocks — how the threads connect, the Tests row, a thread card's text — stay as they are.)

- [ ] **Step 2: Run the tests to watch them fail**

Run: `cd frontend && npx vitest run src/reading/overview.test.ts`
Expected: FAIL — `overviewHeading is not a function` (and the same for the other new names).

- [ ] **Step 3: Write the rules**

In `frontend/src/reading/overview.ts`, replace the head of the file

```ts
/** The overview's connection sentences, Tests row and thread blocks (spec 2026-10-16-outline-and-causes §3). */
import { letter } from "./checks";
import type { Connection, TestsRow, Thread } from "./types";
```

with

```ts
/** The overview's rules (spec 2026-10-25-review-ui-redesign §5): its heading and start button, each thread section's
 * counts, action and connections, the Tests row, the thread intro and the folded rows after the threads. */
import { causeOpen, shown } from "./causes";
import { letter } from "./checks";
import type { Cause, CheckKind, Connection, Mark, Reading, TestsRow, Thread } from "./types";
```

and add at the end of the file:

```ts
/** "5 threads", "1 thread"; "The change" when there are none (§5.1). */
export const overviewHeading = (n: number): string => (n === 0 ? "The change" : n === 1 ? "1 thread" : `${n} threads`);

/** The start button (§5.1): the first unread story in reading order, named by its thread until the reader starts. */
export function startButton(r: Pick<Reading, "order" | "threads">, read: ReadonlySet<string>): { sid: string; label: string } | null {
  const sid = r.order.find((s) => !read.has(s));
  if (!sid) return null;
  if (r.order.some((s) => read.has(s))) return { sid, label: "Continue ›" };
  const i = r.threads.findIndex((t) => t.stories.includes(sid));
  return { sid, label: i < 0 ? "Start here ›" : `Start with Thread ${letter(i, r.threads[i].id)} ›` };
}

/** A thread section's one action (§5.2): Start at its first story, Continue at its first unread one, or all read. */
export type ThreadAction = { kind: "start" | "continue"; sid: string } | { kind: "done" };

export function threadAction(stories: string[], read: ReadonlySet<string>): ThreadAction | null {
  if (!stories.length) return null;
  const unread = stories.find((s) => !read.has(s));
  if (!unread) return { kind: "done" };
  return { kind: stories.some((s) => read.has(s)) ? "continue" : "start", sid: unread };
}

/** A thread section's counts (§5.2): its stories, its shown causes still open (null on a reading without causes), and
 * how many of its stories the reader has read. */
export function threadCounts(t: Thread, causes: Cause[] | null | undefined, hidden: ReadonlySet<CheckKind>,
                             marks: Record<string, Mark>, read: ReadonlySet<string>): { stories: number; open: number | null; read: number } {
  return {
    stories: t.stories.length,
    open: causes ? shown(causes, hidden).filter((c) => c.thread === t.id && causeOpen(c, marks)).length : null,
    read: t.stories.filter((s) => read.has(s)).length,
  };
}

/** How the threads connect (§5.2): each shown connection under the later of its threads, as "With Thread A: …". */
export function sectionConnections(threads: Thread[], conns: Connection[]): Map<string, { text: string; bundled: boolean }[]> {
  const at = new Map(threads.map((t, i) => [t.id, i]));
  const out = new Map<string, { text: string; bundled: boolean }[]>();
  for (const k of conns) {
    const a = at.get(k.a), b = at.get(k.b);
    if (!k.shown || a === undefined || b === undefined || a === b) continue;
    const early = Math.min(a, b), late = threads[Math.max(a, b)].id;
    const row = { text: `With Thread ${letter(early, threads[early].id)}: ${k.text}${k.kind === "bundled" ? " — ask the author" : ""}`,
                  bundled: k.kind === "bundled" };
    out.set(late, [...(out.get(late) ?? []), row]);
  }
  return out;
}

/** The folded rows after the threads (§5.3): Build impact and Coverage only when they have something to say. */
export function foldTitles(r: Pick<Reading, "build_impact" | "coverage" | "rules_only" | "sinks">,
                           comments: { parent_id: number | null; anchor_kind: string }[]):
  { build: string | null; coverage: string | null; discussion: string } {
  const most = Math.max(0, ...r.build_impact.map((b) => b.files));
  const notes = r.coverage.length + (r.rules_only ? 1 : 0) + ((r.sinks?.length ?? 0) > 0 ? 1 : 0);
  const talk = comments.filter((c) => c.parent_id === null && (c.anchor_kind === "review" || c.anchor_kind === "chapter")).length;
  return {
    build: !r.build_impact.length ? null
      : most === 0 ? "Build impact" : `Build impact · up to ${most} ${most === 1 ? "file rebuilds" : "files rebuild"}`,
    coverage: notes ? `Coverage · ${notes} note${notes === 1 ? "" : "s"}` : null,
    discussion: talk ? `Discussion · ${talk} comment${talk === 1 ? "" : "s"}` : "Discussion · no comments yet",
  };
}
```

- [ ] **Step 4: Run the tests to watch them pass**

Run: `cd frontend && npx vitest run src/reading/overview.test.ts && npx tsc --noEmit`
Expected: PASS (all tests in the file, the old ones included); `tsc` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/reading/overview.ts frontend/src/reading/overview.test.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): the overview's rules for thread sections, their counts, connections and folded rows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 8: The overview: a section per thread, counts lined up in columns, the rest folded

**Files:**
- Modify: `frontend/src/workspace/Overview.tsx` (whole file), `frontend/src/workspace/WholePage.tsx` (`Discussion` splits into `DiscussionThreads`), `frontend/src/reading/overview.ts` (`connectionRows` deleted), `frontend/src/reading/overview.test.ts` (its test deleted), `frontend/src/workspace/workspace.css` (the overview block; `.ov-conn-rows`)
- Create: `frontend/e2e/thread-sections.spec.ts`
- Test: `frontend/e2e/helpers.ts` (`openFold`), `frontend/e2e/workspace-reading.spec.ts`, `frontend/e2e/outline-causes.spec.ts`, `frontend/e2e/workspace.spec.ts`, `frontend/e2e/workspace-plan.spec.ts`, `frontend/e2e/workspace-tier1.spec.ts`, `frontend/e2e/workspace-detail.spec.ts`, `frontend/e2e/workspace-sinks.spec.ts`, `frontend/e2e/long-text.spec.ts`

**Interfaces:**
- Consumes: Task 7's `overviewHeading`, `startButton`, `threadAction`, `threadCounts`, `sectionConnections`, `foldTitles`; `AiText`, `AiName` (with `title`), `aiTitle` (Task 1).
- Produces:
  - DOM the e2e tests and Task 9 rely on: root `div.ws-text.ws-whole.ov3` (kept); `h2#ov-whole` with `overviewHeading`; `a.ov-start`; `div.ov-cols[aria-hidden]` with five spans (`""`, `Stories`, `Open`, `Read`, `""`) only when there are threads; per thread `section.ov-sec#thread-<id>[aria-label="Thread A: <plain name>"]` holding `div.ov-sec-head` (`h3.ov-sec-t` > `span.ov-letter`, `b.ov-sec-l`, `span.ov-sec-name[title]`; `span.ov-counts` > three `span.ov-n` whose text is `, <n> <word>` with `.vh` and `.ov-w` parts, and `span.ov-sep`; `span.ov-act` > a link named `Start thread A` / `Continue thread A` or `span.ov-done` `All read ✓`), `div.ov-intro`, `ol.ov-stories`, `button.ov-more[aria-expanded]`, `ul.ov-links`; after the threads `p.ov-tests`; each folded row `section[aria-label="Build impact" | "Coverage" | "Discussion"]` > `details.ov-fold` > `summary` > `h2`.
  - `DiscussionThreads()` (named export of `WholePage.tsx`): the review's comments and each layer's thread, no section or heading.
  - e2e helper `openFold(page: Page, name: "Build impact" | "Coverage" | "Discussion"): Promise<Locator>` — opens that folded row if shut and returns its region.

- [ ] **Step 1: Write the failing e2e tests**

In `frontend/e2e/helpers.ts`, add after `expectNamed`:

```ts
/** Opens one of the overview's folded rows (spec 2026-10-25-review-ui-redesign §5.3) if it is shut; returns its region. */
export async function openFold(page: Page, name: "Build impact" | "Coverage" | "Discussion"): Promise<Locator> {
  const region = page.getByRole("region", { name, exact: true }), fold = region.locator("details.ov-fold");
  await expect(fold).toBeVisible();
  if ((await fold.getAttribute("open")) === null) await region.locator("summary").click();
  await expect(fold).toHaveAttribute("open", "");
  return region;
}
```

Create `frontend/e2e/thread-sections.spec.ts`:

```ts
import { type APIResponse, devices, expect, type Locator, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, openFold, startReview } from "./helpers";

/** The overview's thread sections (spec 2026-10-25-review-ui-redesign §5): fixture CLs 101–104 make three threads, the
 * first two joined by a shared caller, the third only by arriving in CL 104. */
const FOUR = "101 102 103 104";

/** Serves the review's reading with `edit` applied, every time the page asks for it. */
async function patchReading(page: Page, edit: (r: any) => void) {
  await page.route("**/api/reviews/*/reading", async (route) => {
    let res: APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    edit(j);
    await route.fulfill({ response: res, json: j });
  });
}

/** An element's right edge, to the pixel. */
const right = async (l: Locator) => { const b = (await l.boundingBox())!; return Math.round(b.x + b.width); };

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("each thread is a section headed Thread A, B, C, its counts lined up under Stories, Open and Read", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    await expect(page.locator(".ov3 h2").first()).toHaveText("3 threads");
    await expect(page.getByRole("link", { name: "Start with Thread A ›" })).toBeVisible();
    const secs = page.locator("section.ov-sec");
    await expect(secs).toHaveCount(3);
    expect(await secs.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label"))))
      .toEqual(["Thread A: hal_write in hal", "Thread B: logger_init in service", "Thread C: svc::Engine::step in cpp"]);
    await expect(secs.nth(0).locator(".ov-n")).toHaveText([", 2 stories", ", 3 open", ", 0 read"]);
    await expect(secs.nth(1).locator(".ov-n")).toHaveText([", 2 stories", ", 0 open", ", 0 read"]);
    await expect(secs.nth(2).locator(".ov-n")).toHaveText([", 1 story", ", 1 open", ", 0 read"]);
    const labels = page.locator(".ov-cols > span");
    await expect(labels).toHaveText(["", "Stories", "Open", "Read", ""]);
    for (let s = 0; s < 3; s++)
      for (let c = 0; c < 3; c++)
        expect(Math.abs(await right(secs.nth(s).locator(".ov-n").nth(c)) - await right(labels.nth(c + 1))), `section ${s}, column ${c}`)
          .toBeLessThanOrEqual(1);
    await expect(secs.nth(0).locator(".ov-links")).toHaveCount(0);
    await expect(secs.nth(1).locator(".ov-links li")).toHaveText(["With Thread A: both run inside main"]);
    await expect(secs.nth(2).locator(".ov-links li")).toHaveText(["With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    await expectNoNodeIds(page);
    await expectNamed(page);
    await secs.nth(1).getByRole("link", { name: "Start thread B" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S3$`));
    await page.getByRole("button", { name: "Mark as read" }).click();
    await page.goto(base);
    await expect(secs.nth(1).locator(".ov-n").last()).toHaveText(", 1 read");
    await expect(page.getByRole("link", { name: "Continue ›", exact: true })).toBeVisible();
    await secs.nth(1).getByRole("link", { name: "Continue thread B" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S5$`));
    expect((await page.request.put(`/api/reviews/${base.split("/")[2]}/ticks/story/S5`)).ok()).toBe(true);
    await page.goto(base);
    await expect(secs.nth(1).locator(".ov-act")).toHaveText("All read ✓");
  });

  test("a thread with more than four stories shows four, and the others in place", async ({ page }) => {
    await patchReading(page, (r) => { r.threads[0].stories = ["S2", "S1", "S3", "S5", "S4", "S9"]; });
    const base = await startReview(page, FOUR);
    await page.goto(base);
    const a = page.getByRole("region", { name: /^Thread A:/ });
    const items = a.locator(".ov-stories > li");
    await expect(items).toHaveCount(4);
    await expect(a.locator(".ov-n").first()).toHaveText(", 6 stories");
    const { causes } = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/reading`)).json() as
      { causes: { story: string | null; kind: string }[] };
    const opens = (sid: string) => causes.filter((c) => c.story === sid && c.kind !== "confirm").length;
    expect(opens("S2") + opens("S1")).toBe(3);                                       // the thread's 3 open, all on these two
    await expect(items.nth(0).locator(".ov-open")).toHaveText(`, ${opens("S2")} open`);
    await expect(items.nth(1).locator(".ov-open")).toHaveText(`, ${opens("S1")} open`);
    await expect(items.nth(0).getByRole("link")).toHaveAttribute("title", /\S/);   // the whole title on hover
    const more = a.getByRole("button", { name: "Show the other 2 stories ▸" });
    await expect(more).toHaveAttribute("aria-expanded", "false");
    await more.click();
    await expect(items).toHaveCount(6);
    await expect(items.last()).toHaveText("Story S9");                               // a story the review no longer has
    const fewer = a.getByRole("button", { name: "Show fewer ▴" });
    await expect(fewer).toHaveAttribute("aria-expanded", "true");
    await fewer.click();
    await expect(items).toHaveCount(4);
  });

  test("Build impact, Coverage and Discussion are folded rows whose headings say what they hold", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(base);
    await expect(page.locator(".ov3 h2")).toHaveText(["1 thread", "Build impact · up to 4 files rebuild", "Coverage · 2 notes",
                                                      "Discussion · no comments yet"]);
    const cov = page.getByRole("region", { name: "Coverage", exact: true });
    await expect(cov.getByText("Risks judged by rules only.")).toBeHidden();
    await openFold(page, "Coverage");
    await expect(cov.getByText("Risks judged by rules only.")).toBeVisible();
    await page.request.post(`/api/reviews/${base.split("/")[2]}/comments`,
                            { data: { body: "overall: please split the CLs", anchor_kind: "review", anchor: {} } });
    await page.reload();
    const talk = await openFold(page, "Discussion");
    await expect(talk.locator("h2")).toHaveText("Discussion · 1 comment");
    await expect(talk.getByText("overall: please split the CLs")).toBeVisible();
    await expectNamed(page);
  });

  test("a review with no threads says the change and starts here, with no column labels (review focus 2)", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await patchReading(page, (r) => { r.threads = []; r.connections = []; });
    await page.goto(base);
    await expect(page.locator(".ov3 h2").first()).toHaveText("The change");
    await expect(page.locator(".ov-cols, section.ov-sec")).toHaveCount(0);
    await page.getByRole("link", { name: "Start here ›" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2$`));
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the counts wrap under the thread's name with their words, and nothing scrolls sideways", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const a = page.getByRole("region", { name: /^Thread A:/ });
    await expect(a).toBeVisible();
    await expect(page.locator(".ov-cols")).toBeHidden();
    const name = (await a.locator("h3").boundingBox())!, counts = (await a.locator(".ov-counts").boundingBox())!;
    expect(counts.y).toBeGreaterThanOrEqual(name.y + name.height - 1);
    expect((await a.locator(".ov-w").first().boundingBox())!.width).toBeGreaterThan(10);   // "stories" shows
    await expect(a.locator(".ov-sep").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

In `frontend/e2e/long-text.spec.ts`, add at the end of the file:

```ts
test("a long thread name keeps its overview section header on one line, the whole name on hover (review focus 5)", async ({ page }) => {
  const NAME = `${LONG_FN} in ${LONG_DIR.slice(0, -1)}`;
  await page.route("**/api/reviews/*/reading", async (route) => {
    let res: import("@playwright/test").APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    j.threads[0].name = `\`${LONG_FN}\` in ${LONG_DIR.slice(0, -1)}`;
    await route.fulfill({ response: res, json: j });
  });
  const base = await startReview(page);
  await page.goto(base);
  const head = page.locator(".ov-sec-head").first(), name = page.locator(".ov-sec-name").first();
  await expect(head).toBeVisible();
  expect(await oneLine(page, ".ov-sec-name")).toEqual([]);
  expect(await name.evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);         // cut short…
  await expect(name).toHaveAttribute("title", NAME);                                    // …with the whole name on hover
  expect((await head.boundingBox())!.height).toBeLessThan(50);
});
```

In `frontend/e2e/workspace-reading.spec.ts`, replace

```ts
    await expect(page.locator(".ov3 h2")).toHaveText(["The change as a whole", "Threads", "How the threads connect", "Build impact",
                                                      "Coverage", "Discussion"]);
    await expect(page.locator(".ov3 .ws-lead")).toHaveText("3 threads: A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    const threads = page.locator(".ov-thread");
    await expect(threads.locator("h3")).toHaveText(["hal_write in hal", "logger_init in service", "svc::Engine::step in cpp"]);
```

with

```ts
    await expect(page.locator(".ov3 h2")).toHaveText(["3 threads", "Build impact · up to 4 files rebuild", "Coverage · 2 notes",
                                                      "Discussion · no comments yet"]);
    await expect(page.locator(".ov3 .ws-lead")).toHaveText("3 threads: A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
    await expect(page.locator(".ov-links li")).toHaveText(["With Thread A: both run inside main",
                                                           "With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    const threads = page.locator("section.ov-sec");
    await expect(threads.locator(".ov-sec-name")).toHaveText(["hal_write in hal", "logger_init in service", "svc::Engine::step in cpp"]);
```

replace

```ts
    await threads.first().getByRole("link", { name: "Go to thread A's first unread story" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
```

with

```ts
    await threads.first().getByRole("link", { name: "Start thread A" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
```

replace

```ts
  test("the overview gives each thread its intro and a way into its first unread story", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const card = page.locator(".ov-thread").first();
```

with

```ts
  test("the overview gives each thread its intro and a way into its first unread story", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const card = page.locator("section.ov-sec").first();
```

replace

```ts
    await card.getByRole("link", { name: "Go to thread A's first unread story" }).click();
```

with

```ts
    await card.getByRole("link", { name: "Start thread A" }).click();
```

and, in the phone `describe`, replace

```ts
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
```

with

```ts
    await expect(page.locator(".ov-links li")).toHaveText(["With Thread A: both run inside main",
                                                           "With Thread B: nothing besides arriving in CL 104 — ask the author"]);
```

In `frontend/e2e/outline-causes.spec.ts`, replace

```ts
    await expect(page.locator(".ov-meta").first()).toHaveText("2 stories · 0 read");
```

with

```ts
    await expect(page.locator("section.ov-sec").first().locator(".ov-n")).toHaveText([", 2 stories", ", — open", ", 0 read"]);
```

and replace the whole test `the change, Start here then Continue, a block per thread and how they connect; nothing pinned beside it` with:

```ts
  test("the change, Start with Thread A then Continue, a section per thread and how they connect; nothing pinned beside it", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    await expect(page.locator(".ov3 h2")).toHaveText(["3 threads", "Build impact · up to 4 files rebuild", "Coverage · 2 notes",
                                                      "Discussion · no comments yet"]);
    const a = page.getByRole("region", { name: "Thread A: hal_write in hal" });
    await expect(a.locator(".ov-n")).toHaveText([", 2 stories", ", 3 open", ", 0 read"]);
    const intro = a.locator(".ov-intro");
    const full = (await intro.getAttribute("title")) ?? "";
    expect(full.length).toBeGreaterThan(0);
    expect(full).toContain(((await intro.innerText()).split("\n")[0] ?? "").slice(0, 20));
    expect(full).not.toMatch(/\bN\d+\b/);
    await expect(page.locator(".ov-links li")).toHaveText(["With Thread A: both run inside main",
                                                           "With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("Risks judged by rules only.");
    await expect(page.locator(".ov-howto, .ck-tile, .ov-progress, .ov-route, .ov2-check, .ov-thread, .ov-meta, .ov-conn-rows"))
      .toHaveCount(0);
    await page.getByRole("link", { name: "Start with Thread A ›" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2`));
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
    await page.goto(base);
    await expect(a.locator(".ov-n")).toHaveText([", 2 stories", ", 3 open", ", 1 read"]);
    await expect(a.getByRole("link", { name: "Continue thread A" })).toBeVisible();
    await page.getByRole("link", { name: "Continue ›", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
    await page.goto(base);
    await page.getByRole("link", { name: "Start thread B" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S3`));
    await expectNoNodeIds(page);
    await expectNamed(page);
  });
```

In `frontend/e2e/workspace.spec.ts`, replace

```ts
    await expect(ov.locator("h2")).toHaveText(["The change as a whole", "Threads", "How the threads connect", "Build impact",
                                               "Coverage", "Discussion"]);
    await expect(ov.locator(".ws-lead")).toHaveText("One thread: hal_write in hal.");
    await expect(ov).toContainText("One thread: all stories are connected by calls or shared data.");
```

with

```ts
    await expect(ov.locator("h2")).toHaveText(["1 thread", "Build impact · up to 4 files rebuild", "Coverage · 2 notes",
                                               "Discussion · no comments yet"]);
    await expect(ov.locator(".ws-lead")).toHaveText("One thread: hal_write in hal.");
    await expect(ov.locator("section.ov-sec")).toHaveCount(1);
    await expect(ov.locator(".ov-links")).toHaveCount(0);                    // one thread connects to nothing
```

In `frontend/e2e/workspace-plan.spec.ts`, replace

```ts
    const metas = page.locator(".ov-thread .ov-meta");
    for (const m of await metas.allInnerTexts()) expect(m).toMatch(/^(\d+) stor(y|ies) · \1 read( · |$)/);
```

with

```ts
    const secs = page.locator("section.ov-sec");
    await expect(secs.first()).toBeVisible();
    for (const s of await secs.all()) {
      const [stories, , read] = (await s.locator(".ov-n").allTextContents()).map((t) => parseInt(t.replace(/\D+/g, " "), 10));
      expect(read).toBe(stories);
      await expect(s.locator(".ov-act")).toHaveText("All read ✓");
    }
```

and replace

```ts
    await expect(page.locator(".ov-thread .ov-meta").filter({ hasText: " · 1 read" })).toHaveCount(1);   // its thread counts it
```

with

```ts
    await expect(page.locator("section.ov-sec .ov-n").filter({ hasText: /^, 1 read$/ })).toHaveCount(1);   // its thread counts it
```

In `frontend/e2e/workspace-tier1.spec.ts`, replace

```ts
    const intro = page.locator(".ov-thread").first().locator(".ov-purpose");
```

with

```ts
    const intro = page.locator("section.ov-sec").first().locator(".ov-purpose");
```

In `frontend/e2e/workspace-detail.spec.ts`, add `openFold` to the import from `./helpers` and replace

```ts
    const talk = page.locator("section", { has: page.getByRole("heading", { name: "Discussion" }) });
```

with

```ts
    const talk = await openFold(page, "Discussion");
```

In `frontend/e2e/workspace-sinks.spec.ts`, change the helpers import to `import { login, openFold, openIndex, startReview } from "./helpers";`, then replace

```ts
    await page.goto(base);
    await cov.getByRole("button", { name: "Show" }).click();
```

with

```ts
    await page.goto(base);
    await openFold(page, "Coverage");
    await cov.getByRole("button", { name: "Show" }).click();
```

replace

```ts
    await page.goto(base);
    await cov.getByRole("button", { name: "Hide" }).click();
```

with

```ts
    await page.goto(base);
    await openFold(page, "Coverage");
    await cov.getByRole("button", { name: "Hide" }).click();
```

replace

```ts
    await expect(rows).toHaveCount(0);
    await cov.getByRole("button", { name: "Unmark Uart::errors" }).click();
```

with

```ts
    await expect(rows).toHaveCount(0);
    await openFold(page, "Coverage");
    await cov.getByRole("button", { name: "Unmark Uart::errors" }).click();
```

and replace

```ts
    await page.getByRole("region", { name: "Coverage" }).getByRole("button", { name: "Show" }).click();
```

with

```ts
    await (await openFold(page, "Coverage")).getByRole("button", { name: "Show" }).click();
```

- [ ] **Step 2: Build and run the specs to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/thread-sections.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts e2e/workspace.spec.ts e2e/workspace-plan.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-detail.spec.ts e2e/workspace-sinks.spec.ts e2e/long-text.spec.ts`
Expected: FAIL — no `section.ov-sec`, `.ov-cols` or `details.ov-fold` exists yet (e.g. `Expected: "3 threads"`, `Received: "The change as a whole"`).

- [ ] **Step 3: Split the Discussion**

In `frontend/src/workspace/WholePage.tsx`, replace the whole `Discussion` function

```tsx
/** The review's and its layers' comment threads. */
export function Discussion() {
  const d = useWs().data, layerName = layerOf(d);
  return (
    <section aria-labelledby="ws-talk">
      <h2 id="ws-talk">Discussion</h2>
      <Comments reviewId={d.id} comments={d.comments} kind="review" anchor={{}} onChange={d.loadComments} />
```

down to its closing `}` with:

```tsx
/** The review's and its layers' comment threads; the overview folds them under its Discussion row (spec
 * 2026-10-25-review-ui-redesign §5.3). */
export function DiscussionThreads() {
  const d = useWs().data, layerName = layerOf(d);
  return <>
    <Comments reviewId={d.id} comments={d.comments} kind="review" anchor={{}} onChange={d.loadComments} />
    {[...new Set(d.comments.filter((c) => c.anchor_kind === "chapter" && c.parent_id === null)
      .map((c) => (typeof c.anchor.level === "number" ? c.anchor.level : null)))]
      .map((level) => (
        <div key={String(level)} className="bd-layer-thread">
          <div className="m">Layer {layerName(level) ?? (level === null ? "unlayered" : `L${level}`)}</div>
          <Comments reviewId={d.id} comments={d.comments} kind="chapter" anchor={{ level }} onChange={d.loadComments} compact />
        </div>
      ))}
  </>;
}

/** The Discussion section of a review run before the reading. */
function Discussion() {
  return (
    <section aria-labelledby="ws-talk">
      <h2 id="ws-talk">Discussion</h2>
      <DiscussionThreads />
    </section>
  );
}
```

- [ ] **Step 4: Rewrite the overview**

Replace the whole of `frontend/src/workspace/Overview.tsx` with:

```tsx
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import AiText, { AiName } from "../components/AiText";
import SinkMark from "../components/SinkMark";
import { aiTitle } from "../lib/aiMarks";
import { setShowSinks, showSinks, sinkLine } from "../lib/sinks";
import { causeOpen, shown } from "../reading/causes";
import { letter } from "../reading/checks";
import { cardText, foldTitles, overviewHeading, sectionConnections, startButton, testsLine, threadAction,
  threadCounts } from "../reading/overview";
import type { Reading, SinkHit, Thread } from "../reading/types";
import { useWs } from "./context";
import { short } from "./crumbs";
import { plainNames } from "./names";
import { Ticks } from "./NameText";
import { DiscussionThreads } from "./WholePage";

/** A thread's stories shown before "Show the other N stories" (spec 2026-10-25-review-ui-redesign §5.2). */
const SHOWN = 4;

/** One count in a thread's header bar (§5.2): the number under its column label; its word shows only on a phone, where
 * the counts wrap under the name. A screen reader hears ", 2 stories, 3 open, 0 read". */
function Count({ n, word, sep = false }: { n: number | string; word: string; sep?: boolean }) {
  return <>
    {sep && <span className="ov-sep" aria-hidden> · </span>}
    <span className="ov-n"><span className="vh">, </span>{n}<span className="ov-w"> {word}</span></span>
  </>;
}

/** A thread (§5.2): a header bar with its letter, name, counts and one action; its intro; its first stories, the rest a
 * click away; how it connects to the threads before it. */
function ThreadSection({ t, i, r, links }: { t: Thread; i: number; r: Reading; links: { text: string; bundled: boolean }[] }) {
  const ws = useWs(), read = new Set(ws.data.ticks?.stories ?? []);
  const [all, setAll] = useState(false);
  const plain = (s: string) => plainNames(s, ws.data.names).replaceAll("`", "");
  const L = letter(i, t.id), name = plain(t.name);
  const n = threadCounts(t, r.causes, ws.hidden, r.marks, read), act = threadAction(t.stories, read);
  const byId = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st]));
  const causes = shown(r.causes ?? [], ws.hidden);
  const full = cardText(t).map((p) => plain(p.text)).join("\n");
  const more = t.stories.length - SHOWN;
  const to = (sid: string) => ws.link(ws.item({ kind: "story", sid, view: "steps" }));
  return (
    <section className="ov-sec" id={`thread-${t.id}`} aria-label={`Thread ${L}: ${name}`}>
      <div className="ov-sec-head">
        <h3 className="ov-sec-t">
          <span className="ov-letter" aria-hidden>{L}</span>
          <b className="ov-sec-l">Thread {L}</b><span className="vh">: </span>
          <span className="ov-sec-name" title={name}>
            <AiName ai={t.text_source === "llm"} title={`${aiTitle()}\n${name}`}><Ticks text={t.name} /></AiName>
          </span>
        </h3>
        <span className="ov-counts">
          <Count n={n.stories} word={n.stories === 1 ? "story" : "stories"} />
          <Count n={n.open ?? "—"} word="open" sep />
          <Count n={n.read} word="read" sep />
        </span>
        <span className="ov-act">
          {act?.kind === "done" ? <span className="ov-done">All read ✓</span>
            : act && <Link to={to(act.sid)} aria-label={`${act.kind === "start" ? "Start" : "Continue"} thread ${L}`}>
                {act.kind === "start" ? "Start ›" : "Continue ›"}</Link>}
        </span>
      </div>
      <div className="ov-intro" title={full}>{cardText(t).map((p) => (
        <AiText key={p.text} className="ov-purpose" ai={p.ai} title={p.ai ? `${aiTitle()}\n${full}` : undefined}>
          <Ticks text={p.text} /></AiText>
      ))}</div>
      {t.stories.length > 0 && <ol className="ov-stories">{(all ? t.stories : t.stories.slice(0, SHOWN)).map((sid) => {
        const st = byId.get(sid), open = causes.filter((c) => c.story === sid && causeOpen(c, r.marks)).length;
        return (
          <li key={sid}>
            <Link to={to(sid)} title={st ? plain(st.title) : undefined}>{st ? <Ticks text={st.title} /> : `Story ${sid}`}</Link>
            {open > 0 && <span className="ov-open"><span className="vh">, </span>{open} open</span>}
            {read.has(sid) && <span className="ov-read"><span aria-hidden>✓</span><span className="vh">, read</span></span>}
          </li>
        );
      })}</ol>}
      {more > 0 && <button className="link ov-more" aria-expanded={all} onClick={() => setAll(!all)}>
        {all ? "Show fewer ▴" : `Show the other ${more === 1 ? "story" : `${more} stories`} ▸`}</button>}
      {links.length > 0 && <ul className="ov-links">{links.map((k) => (
        <li key={k.text} className={k.bundled ? "bundled" : undefined}><Ticks text={k.text} /></li>
      ))}</ul>}
    </section>
  );
}

/** The shared sinks the review hid (spec 2026-10-09 §5.2), with the viewer's Show/Hide and the owner's unmark. Show is
 * kept in the browser; the page reloads so every board, story and finding list follows it. */
function SinksLine({ hits }: { hits: SinkHit[] }) {
  const shown = showSinks();
  const flip = () => { setShowSinks(!shown); window.location.reload(); };
  return (
    <li className="ov-sinks">
      <Ticks text={sinkLine(hits, shown)} /> · <button className="link" onClick={flip} aria-pressed={shown}>{shown ? "Hide" : "Show"}</button>
      {hits.filter((h) => h.why === "marked").map((h) => <span key={h.label}> · <SinkMark label={h.label} on /></span>)}
    </li>
  );
}

/** A folded row after the threads (§5.3): its summary a heading that says what is inside. */
function Fold({ name, title, children }: { name: string; title: string; children: ReactNode }) {
  return (
    <section aria-label={name}>
      <details className="ov-fold">
        <summary><h2>{title}</h2></summary>
        {children}
      </details>
    </section>
  );
}

/** The overview (§5): how many threads and the change as a whole, where to start, a section per thread with its counts
 * under one row of column labels, the tests, then Build impact, Coverage and Discussion folded. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), ss = ws.data.stories, read = new Set(ws.data.ticks?.stories ?? []);
  const start = startButton(r, read), folds = foldTitles(r, ws.data.comments), links = sectionConnections(r.threads, r.connections);
  const tests = r.tests?.stories[0], testsStory = tests ? ss?.stories.find((s) => s.id === tests) : null;
  return (
    <div className="ws-page"><div className="ws-text ws-whole ov3">
      <section aria-labelledby="ov-whole" className="ov-top">
        <h2 id="ov-whole">{overviewHeading(r.threads.length)}</h2>
        <AiText className="ws-lead" ai={r.whole_source === "llm"}><Ticks text={r.whole} /></AiText>
        {start ? <Link className="ov-start" to={ws.link(ws.item({ kind: "story", sid: start.sid, view: "steps" }))}>{start.label}</Link>
          : r.order.length > 0 && <p className="muted">You've read every story.</p>}
      </section>
      {r.threads.length > 0 && <>
        <div className="ov-cols" aria-hidden><span /><span>Stories</span><span>Open</span><span>Read</span><span /></div>
        {r.threads.map((t, i) => <ThreadSection key={t.id} t={t} i={i} r={r} links={links.get(t.id) ?? []} />)}
        {r.tests && (
          <p className="ov-tests">{testsStory
            ? <Link to={ws.link(ws.item({ kind: "story", sid: testsStory.id, view: "steps" }))}
                    title={`Go to story ${testsStory.id}: ${short(testsStory.title)}`}>{testsLine(r.tests, r.threads)}</Link>
            : testsLine(r.tests, r.threads)}</p>
        )}
      </>}
      {folds.build && <Fold name="Build impact" title={folds.build}>
        <ul className="ov-lines">{r.build_impact.map((b) => (
          <li key={b.header}><Ticks text={b.text} />{b.note && <span className="muted"> {b.note}</span>}</li>
        ))}</ul>
      </Fold>}
      {folds.coverage && <Fold name="Coverage" title={folds.coverage}>
        <ul className="ov-lines">
          {r.rules_only && <li>Risks judged by rules only.</li>}
          {r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}
          {(r.sinks?.length ?? 0) > 0 && <SinksLine hits={r.sinks!} />}
        </ul>
      </Fold>}
      <Fold name="Discussion" title={folds.discussion}><DiscussionThreads /></Fold>
    </div></div>
  );
}
```

- [ ] **Step 5: Delete the old connection rows**

In `frontend/src/reading/overview.ts`, delete the whole `connectionRows` function with its doc comment (from `/** "A and B: both run inside \`main\`", one per shown connection…` to its closing `}`).

In `frontend/src/reading/overview.test.ts`, remove `connectionRows, ` from the import and delete the whole `describe("how the threads connect", …)` block (the one calling `connectionRows`; the new `describe("how the threads connect, under the later thread (§5.2)", …)` stays).

- [ ] **Step 6: Style the sections and folds**

In `frontend/src/workspace/workspace.css`, delete

```css
.ov-conn-rows { margin: 0; padding-left: 18px; font-size: 13px; }
.ov-conn-rows li.bundled { color: var(--accent); }
```

and replace

```css
.ov3 .ov-thread { border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; }
.ov3 .ov-thread header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.ov3 .ov-thread h3 { margin: 0; font-size: 15px; overflow-wrap: anywhere; }
.ov3 .ov-intro { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; margin: 6px 0; }
.ov3 .ov-intro p { margin: 0 0 4px; }
.ov3 .ov-meta { margin: 0 0 4px; color: var(--muted); font-size: 13px; }
```

with

```css
/* a section per thread (spec 2026-10-25-review-ui-redesign §5.2): the header bars and the label row share one grid, so the
   counts line up in columns; the label row's 13px is the header's 12px plus its section's border */
.ov3 .ov-cols, .ov3 .ov-sec-head { display: grid; grid-template-columns: minmax(0, 1fr) 72px 72px 72px 96px; column-gap: 8px;
  align-items: center; }
.ov3 .ov-cols { margin: 22px 0 4px; padding: 0 13px; font-size: 12px; color: var(--muted); }
.ov3 .ov-cols span, .ov3 .ov-n { text-align: right; font-variant-numeric: tabular-nums; }
.ov3 .ov-sec { margin: 0 0 14px; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.ov3 .ov-sec-head { min-height: 40px; padding: 0 12px; background: var(--gap-bg); border-bottom: 1px solid var(--line); }
.ov3 .ov-sec-t { display: flex; align-items: center; gap: 8px; min-width: 0; margin: 0; font-size: 15px; font-weight: 400;
  line-height: 1.3; color: var(--ink); }
.ov3 .ov-sec-l { flex: none; font-weight: 650; }
.ov3 .ov-sec-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ov3 .ov-counts { display: contents; }
.ov3 .ov-n { font-size: 14px; }
.ov3 .ov-w { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.ov3 .ov-sep { display: none; }
.ov3 .ov-act { text-align: right; font-size: 13px; white-space: nowrap; }
.ov3 .ov-act a { font-weight: 600; text-decoration: none; }
.ov3 .ov-done { color: var(--ok); }
.ov3 .ov-intro { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3; overflow: hidden;
  margin: 10px 14px 6px; }
.ov3 .ov-intro p { margin: 0 0 4px; }
.ov3 .ov-stories { margin: 6px 14px 8px; padding-left: 22px; font-size: 14px; }
.ov3 .ov-stories li { padding: 2px 0; overflow-wrap: anywhere; }
.ov3 .ov-stories li::marker { color: var(--muted); }
.ov3 .ov-stories a { text-decoration: none; }
.ov3 .ov-open { margin-left: 8px; font-size: 12px; color: var(--warn); white-space: nowrap; }
.ov3 .ov-read { margin-left: 6px; color: var(--ok); }
.ov3 .ov-more { display: block; margin: 0 14px 10px; font-size: 13px; }
.ov3 .ov-links { margin: 0 14px 10px; padding: 6px 0 0 18px; border-top: 1px dashed var(--line); font-size: 13px; color: var(--muted); }
.ov3 .ov-links li.bundled { color: var(--accent); }
/* Build impact, Coverage and Discussion folded (§5.3): the summary is the heading */
.ov3 .ov-fold { border-top: 1px solid var(--line); }
.ov3 .ov-fold[open] { padding-bottom: 10px; }
.ov3 .ov-fold > summary { display: flex; align-items: center; gap: 8px; padding: 10px 0; cursor: pointer; list-style: none; }
.ov3 .ov-fold > summary::-webkit-details-marker { display: none; }
.ov3 .ov-fold > summary::after { content: "▸"; margin-left: auto; color: var(--muted); }
.ov3 .ov-fold[open] > summary::after { content: "▾"; }
.ov3 .ov-fold > summary h2 { margin: 0; }
@media (max-width: 640px) {
  .ov3 .ov-cols { display: none; }
  .ov3 .ov-sec-head { display: flex; flex-wrap: wrap; column-gap: 8px; row-gap: 2px; padding: 8px 12px; }
  .ov3 .ov-sec-t { flex: 1 1 0; }
  .ov3 .ov-act { order: 1; }
  .ov3 .ov-counts { display: block; order: 2; flex-basis: 100%; padding-left: 28px; font-size: 13px; color: var(--muted); }
  .ov3 .ov-n { font-size: inherit; }
  .ov3 .ov-w { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
  .ov3 .ov-sep { display: inline; }
}
```

- [ ] **Step 7: Check, build and run the specs to watch them pass**

Run: `cd frontend && npx vitest run src/reading && npx tsc --noEmit && npm run build && E2E e2e/thread-sections.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts e2e/workspace.spec.ts e2e/workspace-plan.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-detail.spec.ts e2e/workspace-sinks.spec.ts e2e/long-text.spec.ts e2e/workspace-layout.spec.ts e2e/workspace-legacy.spec.ts`
Expected: vitest PASS, `tsc` prints nothing, every spec PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/workspace/Overview.tsx frontend/src/workspace/WholePage.tsx frontend/src/reading/overview.ts frontend/src/reading/overview.test.ts frontend/src/workspace/workspace.css frontend/e2e/thread-sections.spec.ts frontend/e2e/helpers.ts frontend/e2e/workspace-reading.spec.ts frontend/e2e/outline-causes.spec.ts frontend/e2e/workspace.spec.ts frontend/e2e/workspace-plan.spec.ts frontend/e2e/workspace-tier1.spec.ts frontend/e2e/workspace-detail.spec.ts frontend/e2e/workspace-sinks.spec.ts frontend/e2e/long-text.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(overview): a section per thread with its counts in columns; build impact, coverage and discussion folded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 9: The outline: one thread open at a time, the other bars pinned

**Files:**
- Create: `frontend/src/workspace/outline.ts`, `frontend/src/workspace/outline.test.ts`
- Modify: `frontend/src/workspace/Outline.tsx` (imports; `StoriesView`), `frontend/src/workspace/workspace.css` (bars, numbers)
- Test: `frontend/e2e/helpers.ts` (`railReady`, `storyLink`, `barNames`; `startReview` waits with `railReady`), `frontend/e2e/thread-sections.spec.ts` (the accordion), `frontend/e2e/long-text.spec.ts`, and the specs that click the outline's story rows: `ai.spec.ts`, `banner.spec.ts`, `landing.spec.ts`, `workspace-map-stories.spec.ts`, `workspace-sequence.spec.ts`, `workspace-story.spec.ts`, `workspace-tier1.spec.ts`, `workspace.spec.ts`, `workspace-layout.spec.ts`, `workspace-plan.spec.ts`, `workspace-reading.spec.ts`, `outline-causes.spec.ts`, `theme.spec.ts`

**Interfaces:**
- Consumes: `load`, `save` (`board/prefs.ts`); `threadRead` (`reading/plan.ts`); `plainNames` (`workspace/names.ts`).
- Produces (exported from `src/workspace/outline.ts`):
  - `BAR = 36` — a thread bar's height in px.
  - `loadThread(rid: number): string | null`, `saveThread(rid: number, id: string | null): void` — key `ct.ws.<rid>.thread`.
  - `openThread(threads: { id: string; stories: string[] }[], story: string | null, last: string | null): string | null`.
  - `barPin(i: number, open: number, n: number): { top: number } | { bottom: number } | null` — `open` is the open thread's index, `-1` for none.
  - DOM: per thread `h3.ws-bar` (`.on` when open; sticky offsets inline) > `button[aria-expanded][title="Thread A: <name>"][aria-label="Thread A: <name>[, N open][, x of y read]"]`; the open thread's stories in `ul.ws-bar-list`, each row numbered (`span.ws-num`); `⌂ Overview` without the risk pill. Task 14 replaces `StoryFlows` under the current story.
  - e2e helpers: `railReady(page)`, `storyLink(page, name: RegExp): Promise<Locator>`, `barNames(page): Promise<(string | null)[]>`.

- [ ] **Step 1: Write the failing unit tests**

Create `frontend/src/workspace/outline.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BAR, barPin, loadThread, openThread, saveThread } from "./outline";

const threads = [{ id: "T1", stories: ["S2", "S1"] }, { id: "T2", stories: ["S3", "S5"] }, { id: "T3", stories: ["S4"] }];

describe("which thread the outline opens (spec 2026-10-25-review-ui-redesign §6)", () => {
  it("opens the thread holding the current story, whatever was opened last", () => {
    expect(openThread(threads, "S5", "T1")).toBe("T2");
    expect(openThread(threads, "S1", null)).toBe("T1");
  });

  it("elsewhere opens the thread last opened if the reading still has it, else none", () => {
    expect(openThread(threads, null, "T3")).toBe("T3");
    expect(openThread(threads, "S9", "T3")).toBe("T3");                      // a story in no thread
    expect(openThread(threads, null, "T9")).toBeNull();
    expect(openThread(threads, null, null)).toBeNull();
    expect(openThread([], "S1", "T1")).toBeNull();
  });
});

describe("where the closed bars pin (§6)", () => {
  it("pins the bars up to the open one at the top, stacked, and the rest at the bottom, stacked from the last", () => {
    expect(BAR).toBe(36);
    expect([0, 1, 2, 3].map((i) => barPin(i, 1, 4))).toEqual([{ top: 0 }, { top: 36 }, { bottom: 36 }, { bottom: 0 }]);
    expect([0, 1, 2].map((i) => barPin(i, 2, 3))).toEqual([{ top: 0 }, { top: 36 }, { top: 72 }]);
    expect([0, 1].map((i) => barPin(i, 0, 2))).toEqual([{ top: 0 }, { bottom: 0 }]);
  });

  it("pins nothing while no thread is open", () => {
    expect(barPin(0, -1, 3)).toBeNull();
    expect(barPin(2, -1, 3)).toBeNull();
  });
});

describe("the thread last opened, kept per review", () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = new Map();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps it under ct.ws.<review id>.thread, apart from other reviews", () => {
    expect(loadThread(12)).toBeNull();
    saveThread(12, "T2");
    expect(store.get("ct.ws.12.thread")).toBe('"T2"');
    expect(loadThread(12)).toBe("T2");
    expect(loadThread(13)).toBeNull();
    saveThread(12, null);
    expect(loadThread(12)).toBeNull();
  });

  it("reads a stored value of the wrong shape as none", () => {
    store.set("ct.ws.12.thread", "42");
    expect(loadThread(12)).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npx vitest run src/workspace/outline.test.ts`
Expected: FAIL — `Failed to resolve import "./outline"`.

- [ ] **Step 3: Write the rules**

Create `frontend/src/workspace/outline.ts`:

```ts
/** The outline's threads as an accordion (spec 2026-10-25-review-ui-redesign §6): which one is open, where the closed
 * bars pin, and the thread the viewer last opened in a review. Pure, so the rules are tested apart from React. */
import { load, save } from "../board/prefs";

/** A thread bar's fixed height in px: pinned bars stack by it. */
export const BAR = 36;

const key = (rid: number) => `ct.ws.${rid}.thread`;

/** The thread the viewer last opened in this review; a stored value of the wrong shape counts as none. */
export function loadThread(rid: number): string | null {
  const v = load<unknown>(key(rid), null);
  return typeof v === "string" ? v : null;
}

export const saveThread = (rid: number, id: string | null) => save(key(rid), id);

/** The open thread: the one holding the current story; anywhere else the one last opened, if the reading still has it. */
export function openThread(threads: { id: string; stories: string[] }[], story: string | null, last: string | null): string | null {
  const holding = story ? threads.find((t) => t.stories.includes(story)) : undefined;
  if (holding) return holding.id;
  return last && threads.some((t) => t.id === last) ? last : null;
}

/** Where the i-th of n bars pins while the thread at index `open` is open: up to it at the top, stacked; after it at the
 * bottom, stacked from the last; nothing pins while none is open (`open` -1). */
export function barPin(i: number, open: number, n: number): { top: number } | { bottom: number } | null {
  if (open < 0) return null;
  return i <= open ? { top: i * BAR } : { bottom: (n - 1 - i) * BAR };
}
```

- [ ] **Step 4: Run the unit tests**

Run: `cd frontend && npx vitest run src/workspace/outline.test.ts && npx tsc --noEmit`
Expected: PASS (5 tests); `tsc` prints nothing.

- [ ] **Step 5: Commit the rules**

```bash
git add frontend/src/workspace/outline.ts frontend/src/workspace/outline.test.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(outline): which thread is open, where the closed bars pin, and the thread kept per review

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

- [ ] **Step 6: Write the failing e2e tests**

In `frontend/e2e/helpers.ts`, replace the line in `startReview`

```ts
  await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first()).toBeVisible({ timeout: 60_000 });
```

with

```ts
  await railReady(page);
```

and add after `startReview`:

```ts
/** Waits for the outline's first thread bar or story row (a review without threads, or before the reading, has rows). */
export async function railReady(page: Page) {
  const rail = page.locator(".ws-rail");
  await expect(rail.getByRole("button", { name: /^Thread \w+:/ }).or(rail.getByRole("link", { name: /^Go to story/ })).first())
    .toBeVisible({ timeout: 60_000 });
}

/** A story's row in the outline, opening thread bars in turn until it shows (spec 2026-10-25-review-ui-redesign §6: one
 * thread open at a time). */
export async function storyLink(page: Page, name: RegExp): Promise<Locator> {
  const rail = page.locator(".ws-rail"), link = rail.getByRole("link", { name }).first();
  const bars = rail.getByRole("button", { name: /^Thread \w+:/ });
  await expect(bars.or(link).first()).toBeVisible({ timeout: 60_000 });
  if (await link.isVisible()) return link;
  for (let i = 0; i < await bars.count(); i++) {
    const bar = bars.nth(i);
    if ((await bar.getAttribute("aria-expanded")) !== "true") await bar.click();
    if (await link.waitFor({ state: "visible", timeout: 1000 }).then(() => true, () => false)) return link;
  }
  return link;
}

/** The outline's thread bars' names, top to bottom. */
export const barNames = (page: Page) =>
  page.locator(".ws-rail .ws-bar > button").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
```

In `frontend/e2e/thread-sections.spec.ts`, add inside `test.describe("desktop", …)` (and add `barNames` to its helpers import):

```ts
  test("the outline opens one thread at a time, keeps it per review, and pins the other bars to its top and bottom", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 320 });                      // short, so the outline scrolls
    const base = await startReview(page, FOUR);
    const rail = page.locator("aside.ws-outline"), box = rail.locator(".ws-rail-scroll");
    const bar = (L: string) => rail.getByRole("button", { name: new RegExp(`^Thread ${L}:`) });
    await expect.poll(() => barNames(page)).toEqual(["Thread A: hal_write in hal, 3 open, 0 of 2 read",
      "Thread B: logger_init in service, 0 of 2 read", "Thread C: svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await expect(rail.locator(".ws-bar-list")).toHaveCount(0);                     // a fresh review opens none
    await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveText("⌂ Overview");   // the header has the risk
    await page.goto(`${base}/s/S3`);
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");               // the current story's thread
    await expect(bar("A")).toHaveAttribute("aria-expanded", "false");
    await expect(rail.locator(".ws-bar-list > li > .ws-row.story .ws-num")).toHaveText(["1", "2"]);
    const edges = async () => { const b = (await box.boundingBox())!; return { top: b.y, bottom: b.y + b.height }; };
    await box.evaluate((e) => { e.scrollTop = 0; });
    const c = (await bar("C").boundingBox())!;
    expect(Math.abs(c.y + c.height - (await edges()).bottom)).toBeLessThanOrEqual(1);   // C pinned at the bottom
    await box.evaluate((e) => { e.scrollTop = e.scrollHeight; });
    await expect.poll(async () => Math.round((await bar("A").boundingBox())!.y - (await edges()).top)).toBe(0);
    expect(Math.round((await bar("B").boundingBox())!.y - (await edges()).top)).toBe(36);   // A and B pinned at the top
    await bar("A").click();                                                       // another bar opens, the open one shuts
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");
    await expect(bar("B")).toHaveAttribute("aria-expanded", "false");
    await bar("A").click();                                                       // the open bar shuts
    await expect(rail.locator(".ws-bar-list")).toHaveCount(0);
    await bar("C").click();
    await page.goto(base);
    await expect(bar("C")).toHaveAttribute("aria-expanded", "true");               // kept for this review
    expect(await page.evaluate((k) => localStorage.getItem(k), `ct.ws.${base.split("/")[2]}.thread`)).toBe('"T3"');
    await page.goto(`${base}/s/S1`);
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");               // going to a story opens its thread
    await expect(bar("C")).toHaveAttribute("aria-expanded", "false");
    await expectNamed(page);
  });
```

In `frontend/e2e/long-text.spec.ts`, in the test `a long thread name keeps its overview section header on one line…` (Task 8), rename it to `a long thread name keeps its overview section header and its outline bar on one line, the whole name on hover (review focus 5)` and replace its last line

```ts
  expect((await head.boundingBox())!.height).toBeLessThan(50);
});
```

with

```ts
  expect((await head.boundingBox())!.height).toBeLessThan(50);
  const bar = page.locator(".ws-rail .ws-bar > button").first();
  expect(await oneLine(page, ".ws-rail .ws-bar .ws-one")).toEqual([]);
  expect(await bar.locator(".ws-one").evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);
  await expect(bar).toHaveAttribute("title", `Thread A: ${NAME}`);
  expect((await page.locator(".ws-rail .ws-bar").first().boundingBox())!.height).toBe(36);
  expect(await problems(page)).toEqual([]);
});
```

Change the helpers imports — `ai.spec.ts`, `banner.spec.ts`, `workspace-map-stories.spec.ts`, `workspace-sequence.spec.ts`, `workspace-story.spec.ts`, `workspace-tier1.spec.ts`, `workspace.spec.ts`, `workspace-layout.spec.ts`, `workspace-plan.spec.ts`: add `storyLink`; `landing.spec.ts`: add `railReady`; `workspace-reading.spec.ts`, `outline-causes.spec.ts`: add `barNames` and `storyLink`.

Then, story rows reached from a page where their thread is shut:

- `ai.spec.ts` — replace both occurrences of
  ```ts
      await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
  ```
  with
  ```ts
      await (await storyLink(page, /^Go to story S1/)).click();
  ```
- `workspace-layout.spec.ts`, `workspace-story.spec.ts` — the same replacement, every occurrence (in `workspace-story.spec.ts` the legacy test's `rail.getByRole("link", { name: /^Go to story S1/ })` is a different line and stays).
- `workspace-story.spec.ts` (phone) and `workspace.spec.ts` (phone) — replace
  ```ts
      await page.getByRole("link", { name: /^Go to story S1/ }).click();
  ```
  with
  ```ts
      await (await storyLink(page, /^Go to story S1/)).click();
  ```
- `banner.spec.ts` — replace
  ```ts
        await page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first().click();
  ```
  with
  ```ts
        await (await storyLink(page, /^Go to story/)).click();
  ```
- `landing.spec.ts` — replace
  ```ts
      await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first()).toBeVisible({ timeout: 60_000 }); // a review opens on its workspace
  ```
  with
  ```ts
      await railReady(page);                                                   // a review opens on its workspace
  ```
- `workspace-map-stories.spec.ts` — replace
  ```ts
      await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).hover();
  ```
  with
  ```ts
      await (await storyLink(page, /^Go to story S1/)).hover();
  ```
- `workspace-sequence.spec.ts` — replace
  ```ts
      await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S\d+: .*logger_init/ }).click();
  ```
  with
  ```ts
      await (await storyLink(page, /^Go to story S\d+: .*logger_init/)).click();
  ```
- `workspace-tier1.spec.ts` — replace
  ```ts
      const rail = page.locator(".ws-rail");
      const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
  ```
  with
  ```ts
      const s1 = await storyLink(page, /^Go to story S1/);
  ```
  replace
  ```ts
      const s3 = page.locator(".ws-rail").getByRole("link", { name: /^Go to story S3/ });
  ```
  with
  ```ts
      const s3 = await storyLink(page, /^Go to story S3/);
  ```
  and replace
  ```ts
      await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ })).toBeVisible({ timeout: 60_000 });
  ```
  with
  ```ts
      await expect(await storyLink(page, /^Go to story S1/)).toBeVisible();
  ```
- `workspace.spec.ts` — replace
  ```ts
      await expect(rail.locator(".ws-thread h3")).toHaveText([/^A hal_write in hal\b/]);
      await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("aria-current", "page");
      const home = (await rail.locator(".ws-home").boundingBox())!, first = (await rail.locator(".ws-thread").first().boundingBox())!;
  ```
  with
  ```ts
      await expect(rail.getByRole("button", { name: /^Thread A: hal_write in hal\b/ })).toHaveAttribute("aria-expanded", "false");
      await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("aria-current", "page");
      const home = (await rail.locator(".ws-home").boundingBox())!, first = (await rail.locator(".ws-bar").first().boundingBox())!;
  ```
  replace
  ```ts
      const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
  ```
  with
  ```ts
      const s1 = await storyLink(page, /^Go to story S1/);
  ```
  replace
  ```ts
      await rail.getByRole("link", { name: /^Go to story S2/ }).click();
  ```
  with
  ```ts
      await (await storyLink(page, /^Go to story S2/)).click();
  ```
  and, in `the rail's grip straddles its border…`, replace
  ```ts
      await page.setViewportSize({ width: 1440, height: 300 });
      await startReview(page);
      const rail = page.locator(".ws-rail");
  ```
  with (one thread open, so the outline is long enough to scroll)
  ```ts
      await page.setViewportSize({ width: 1440, height: 300 });
      await startReview(page);
      const rail = page.locator(".ws-rail");
      await rail.getByRole("button", { name: /^Thread A:/ }).click();
  ```
- `workspace-plan.spec.ts` — replace
  ```ts
      await expect(rail.locator(".ws-read", { hasText: "✓" })).toHaveCount(order.length - 1);
      await expect(rail.getByRole("link", { name: new RegExp(`^Go to story ${order[0]}: .* \\(read\\)`) })).toBeVisible();
      await expect(rail.locator(".ws-thread .ws-thread-read").first()).toHaveText(/^, \d+ of \d+ read$/);
  ```
  with
  ```ts
      const readInBars = async () => (await rail.locator(".ws-bar > button").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? "")))
        .reduce((n, label) => n + Number(/, (\d+) of \d+ read$/.exec(label)?.[1] ?? 0), 0);
      await expect.poll(readInBars).toBe(order.length - 1);
      await expect(await storyLink(page, new RegExp(`^Go to story ${order[0]}: .* \\(read\\)`))).toBeVisible();
      await expect(rail.locator(".ws-bar .ws-thread-read").first()).toHaveText(/^\d+ of \d+$/);
  ```
- `workspace-reading.spec.ts` — replace
  ```ts
      await expect(outline.getByRole("link", { name: "Go to the overview" })).toContainText("Medium risk");
      await expect(outline.locator(".ws-thread h3")).toHaveText(["A hal_write in hal, 3 open, 0 of 2 read", "B logger_init in service, 0 of 2 read",
                                                                 "C svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
      await expect(outline.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ })).toHaveCount(2);
      await expect(outline.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ }).nth(1)).toHaveAccessibleName(/^Go to story S1/);
      await outline.getByRole("link", { name: /^Go to story S1/ }).click();
  ```
  with
  ```ts
      await expect(outline.getByRole("link", { name: "Go to the overview" })).toHaveText("⌂ Overview");   // the header has the risk
      await expect.poll(() => barNames(page)).toEqual(["Thread A: hal_write in hal, 3 open, 0 of 2 read",
        "Thread B: logger_init in service, 0 of 2 read", "Thread C: svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
      await outline.getByRole("button", { name: /^Thread A:/ }).click();
      const rows = outline.locator(".ws-bar-list > li > .ws-row.story");
      await expect(rows).toHaveCount(2);
      await expect(rows.nth(1)).toHaveAccessibleName(/^Go to story S1/);
      await rows.nth(1).click();
  ```
- `outline-causes.spec.ts` — in the first test's loop, replace
  ```ts
      await expect(page.locator(".ws-outline").getByRole("link", { name: /^Go to story S1/ })).toBeVisible();
      expect(await page.evaluate(() => (window as unknown as { old: string[] }).old)).toEqual([]);
  ```
  with
  ```ts
      await expect(page.locator(".ws-outline").getByRole("button", { name: /^Thread A:/ })).toBeVisible();
      expect(await page.evaluate(() => (window as unknown as { old: string[] }).old)).toEqual([]);
  ```
  in `the outline comes back scrolled where the reader left it…`, replace
  ```ts
      await page.setViewportSize({ width: 1440, height: 400 });          // short, so the outline scrolls
      const base = await startReview(page, FOUR);
  ```
  with
  ```ts
      await page.setViewportSize({ width: 1440, height: 300 });          // short, so the outline scrolls
      const base = await startReview(page, FOUR);
      await page.locator("aside.ws-outline").getByRole("button", { name: /^Thread A:/ }).click();   // kept, so it reopens
  ```
  replace
  ```ts
      await expect(outline.locator(".ws-thread h3")).toHaveText(["A hal_write in hal, 3 open, 0 of 2 read",
        "B logger_init in service, 0 of 2 read", "C svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
      await outline.getByRole("link", { name: /^Go to story S1/ }).click();
  ```
  with
  ```ts
      await expect.poll(() => barNames(page)).toEqual(["Thread A: hal_write in hal, 3 open, 0 of 2 read",
        "Thread B: logger_init in service, 0 of 2 read", "Thread C: svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
      await (await storyLink(page, /^Go to story S1/)).click();
  ```
  replace
  ```ts
      await expect(outline.locator(".ws-thread h3").first()).toHaveText("A hal_write in hal, 0 of 2 read");
  ```
  with
  ```ts
      await expect.poll(async () => (await barNames(page))[0]).toBe("Thread A: hal_write in hal, 0 of 2 read");
  ```
  and replace
  ```ts
      await outline.getByRole("link", { name: /^Go to story S1/ }).click();
      await outline.getByRole("link", { name: /^Go to flow 1:/ }).click();
  ```
  with
  ```ts
      await (await storyLink(page, /^Go to story S1/)).click();
      await outline.getByRole("link", { name: /^Go to flow 1:/ }).click();
  ```
- `theme.spec.ts` — delete the line (the outline no longer carries the risk pill)
  ```ts
    ".ws-rail .ct-headline",         // what to act on, in the rail
  ```

- [ ] **Step 7: Build and run the specs to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/thread-sections.spec.ts e2e/long-text.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts`
Expected: FAIL — no button named `Thread A: …` in the outline (`railReady` and `barNames` find none).

- [ ] **Step 8: Build the accordion**

In `frontend/src/workspace/Outline.tsx`, replace the imports

```tsx
import { useEffect, useRef, useState } from "react";
```

with

```tsx
import { Fragment, useEffect, useRef, useState } from "react";
```

delete

```tsx
import HeadlinePill from "../components/HeadlinePill";
```

and add after `import { plainNames } from "./names";`:

```tsx
import { barPin, loadThread, openThread, saveThread } from "./outline";
```

Replace the whole `StoriesView` function (from its doc comment `/** Stories (§1.2): the overview, each thread with its stories in reading order…` to its closing `}`) with:

```tsx
/** Stories (spec 2026-10-25-review-ui-redesign §6): the overview; a bar per thread, one open at a time with its stories
 * numbered and the current story's flows, the bars before it pinned to the top of the scroll area and those after it to
 * the bottom; the tests; the Index folded at the bottom. */
function StoriesView({ r, onPick }: { r: Reading; onPick: () => void }) {
  const ws = useWs(), d = ws.data, ss = d.stories;
  const byId = new Map((ss?.stories ?? []).map((st) => [st.id, st]));
  const list = shown(r.causes ?? [], ws.hidden);
  const open = (pick: (c: Cause) => boolean) => list.filter((c) => pick(c) && causeOpen(c, r.marks)).length;
  const read = d.ticks ? new Set(d.ticks.stories) : null;
  const here = ws.addr.place.kind === "story" ? ws.addr.place.sid : null;
  const tests = (ss?.stories ?? []).filter((st) => st.kind === "tests");
  const [last, setLast] = useState(() => loadThread(d.id));
  const [chosen, setChosen] = useState<{ here: string | null; id: string | null } | null>(null);   // a bar clicked at `here`
  const holding = here ? r.threads.find((t) => t.stories.includes(here))?.id ?? null : null;
  useEffect(() => {                                        // going to a story opens its thread, and the outline keeps it
    if (!holding) return;
    setLast(holding);
    saveThread(d.id, holding);
  }, [holding, d.id]);
  const on = chosen && chosen.here === here ? chosen.id : openThread(r.threads, here, last);
  const at = r.threads.findIndex((t) => t.id === on);
  const toggle = (id: string) => {
    const next = on === id ? null : id;
    setChosen({ here, id: next });
    setLast(next);
    saveThread(d.id, next);
  };
  const story = (st: Story, why?: string, num?: number) => {
    const n = open((c) => c.story === st.id), reason = st.kind === "unsorted" ? "Needs a person to place it" : why;
    const label = `Go to story ${st.id}: ${short(st.title)}${read?.has(st.id) ? " (read)" : ""}${n ? `, ${n} open` : ""}`;
    const place: Place = { kind: "story", sid: st.id, view: "steps" };
    return (
      <li key={st.id}>
        <Link to={ws.link(ws.item(place))} className="ws-row story" aria-current={here === st.id ? "page" : undefined}
              title={bare(st.title)} aria-label={label} onClick={onPick}
              onMouseEnter={() => ws.setHover(st.id)} onMouseLeave={() => ws.setHover(null)}
              onFocus={() => ws.setHover(st.id)} onBlur={() => ws.setHover(null)}>
          <span className="ws-row-top">
            {num !== undefined && <span className="ws-num" aria-hidden>{num}</span>}
            {read && <span className="ws-read" aria-hidden>{read.has(st.id) ? "✓" : ""}</span>}
            <span className="ws-one"><Ticks text={st.title} /></span>
            {n > 0 && <span className="ck-count" aria-hidden>{n}</span>}
          </span>
          {reason && <span className="ws-row-sub">{reason}</span>}
        </Link>
        {here === st.id && <StoryFlows sid={st.id} onPick={onPick} />}
      </li>
    );
  };
  return <>
    <Link to={ws.base} state={{ page: true }} className="ws-row ws-home" aria-current={ws.addr.place.kind === "whole" ? "page" : undefined}
          title="Go to the overview" aria-label="Go to the overview" onClick={onPick}>
      <span aria-hidden>⌂</span> Overview
    </Link>
    {r.threads.map((t, i) => {
      const n = open((c) => c.thread === t.id), L = letter(i, t.id), name = bare(plainNames(t.name, d.names)), isOn = t.id === on;
      return (
        <Fragment key={t.id}>
          <h3 className={`ws-bar${isOn ? " on" : ""}`} style={barPin(i, at, r.threads.length) ?? undefined}>
            <button aria-expanded={isOn} title={`Thread ${L}: ${name}`} onClick={() => toggle(t.id)}
                    aria-label={`Thread ${L}: ${name}${n ? `, ${n} open` : ""}${read ? `, ${threadRead(t.stories, read)} read` : ""}`}>
              <span className="ov-letter" aria-hidden>{L}</span>
              <b className="ws-bar-l">Thread {L}</b>
              <span className="ws-one"><Ticks text={t.name} /></span>
              {n > 0 && <span className="ck-count">{n}</span>}
              {read && <span className="ws-thread-read">{threadRead(t.stories, read)}</span>}
              <span className="ws-bar-caret" aria-hidden>{isOn ? "▾" : "▸"}</span>
            </button>
          </h3>
          {isOn && <ul className="ws-bar-list">{t.stories.map((sid, k) => {
            const st = byId.get(sid);
            return st ? story(st, r.reasons[sid], k + 1) : null;
          })}</ul>}
        </Fragment>
      );
    })}
    {tests.length > 0 && <div className="ws-group"><h3>Tests</h3><ul>{tests.map((st) => story(st))}</ul></div>}
    {!r.threads.length && !tests.length && <p className="muted small ws-pad">No changed functions.</p>}
    <details className="ws-index">
      <summary>Index</summary>
      <ul>{INDEX_TABS.map((t) => (
        <li key={t}><Link to={ws.link(ws.item({ kind: "index", tab: t }))} className="ws-row ws-index-row"
                          aria-label={`Open the Index: ${INDEX_LABEL[t]}`} title={`Open the Index: ${INDEX_LABEL[t]}`} onClick={onPick}>
          <span className="ws-row-top">{INDEX_LABEL[t]}</span></Link></li>
      ))}</ul>
    </details>
  </>;
}
```

In `frontend/src/workspace/workspace.css`, after the line

```css
.ws-index > summary { padding: 4px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
```

add:

```css
/* the outline's thread bars (spec 2026-10-25-review-ui-redesign §6): one thread open at a time; the bars before it pin to
   the top of the scroll area and those after it to the bottom (offsets from barPin), 36px each */
.ws-bar { position: sticky; z-index: 2; height: 36px; box-sizing: border-box; margin: 0; background: var(--surface);
  border-bottom: 1px solid var(--line); font: 400 13px/1.3 var(--sans); }
.ws-bar > button { display: flex; align-items: center; gap: 6px; width: 100%; height: 100%; padding: 0 12px 0 14px; border: 0;
  border-radius: 0; background: none; color: var(--ink); font: inherit; text-align: left; cursor: pointer; }
.ws-bar > button:hover { background: var(--gap-bg); }
.ws-bar.on > button { background: color-mix(in srgb, var(--accent) 8%, var(--surface)); }
.ws-bar .ov-letter { width: 18px; height: 18px; font-size: 10px; }
.ws-bar-l { flex: none; font-weight: 650; }
.ws-bar .ck-count, .ws-bar .ws-thread-read { flex: none; margin-left: 0; }
.ws-bar-caret { flex: none; width: 10px; color: var(--muted); }
.ws-rail .ws-bar-list { padding: 2px 0 6px; }
.ws-num { flex: none; min-width: 1.2em; color: var(--muted); font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; }
```

- [ ] **Step 9: Check, build and run the specs**

Run: `cd frontend && npx tsc --noEmit && npm run build && E2E e2e/thread-sections.spec.ts e2e/long-text.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts e2e/ai.spec.ts e2e/banner.spec.ts e2e/landing.spec.ts e2e/workspace-map-stories.spec.ts e2e/workspace-sequence.spec.ts e2e/workspace-story.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace.spec.ts e2e/workspace-layout.spec.ts e2e/workspace-plan.spec.ts e2e/theme.spec.ts`
Expected: `tsc` prints nothing; every spec PASS.

- [ ] **Step 10: Commit the accordion**

```bash
git add frontend/src/workspace/Outline.tsx frontend/src/workspace/workspace.css frontend/e2e
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(outline): thread bars open one thread at a time and pin to the outline's edges

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

- [ ] **Step 11: Phase 2 gate — the whole suite**

Run: `cd backend && env PYTHONPATH=$PWD .venv/bin/python -m pytest -q -p no:cacheprovider tests && cd ../frontend && npx vitest run && npm run build && E2E 2>&1 | tail -40; rm -rf $(git rev-parse --show-toplevel)/.pwtmp`
Expected: pytest, vitest and every e2e spec PASS. A failure in a spec this phase did not touch is investigated (superpowers:systematic-debugging), not skipped.

- [ ] **Step 12: Phase 2 screenshots for the owner**

Create the scratch spec `frontend/e2e/zz-shots.spec.ts` (never committed):

```ts
import { test } from "@playwright/test";
import { startReview } from "./helpers";

const OUT = "../.superpowers/screens/phase-2";

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test("phase 2", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page, "101 102 103 104");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/overview.png`, fullPage: true });
    await page.goto(`${base}/s/S3`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/outline-open-thread.png` });
  });
});

test.describe("short window", () => {
  test.use({ viewport: { width: 1440, height: 420 } });
  test("phase 2 pinned bars", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page, "101 102 103 104");
    await page.goto(`${base}/s/S3`);
    await page.waitForLoadState("networkidle");
    await page.locator(".ws-rail-scroll").evaluate((e) => { e.scrollTop = e.scrollHeight; });
    await page.screenshot({ path: `${OUT}/outline-pinned.png` });
  });
});

test.describe("phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("phase 2 phone", async ({ page }) => {
    test.setTimeout(240_000);
    await startReview(page, "101 102 103 104");
    await page.getByRole("link", { name: "Go to the overview" }).click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/overview-phone.png`, fullPage: true });
  });
});
```

Run: `cd frontend && E2E e2e/zz-shots.spec.ts; rm e2e/zz-shots.spec.ts; rm -rf $(git rev-parse --show-toplevel)/.pwtmp; ls ../.superpowers/screens/phase-2 && git status --short`
Expected: four PNGs listed; `git status` shows no file this step made. Send the PNGs to the owner (SendUserFile, when the session has it) with one line: "Phase 2: a section per thread with counts in columns; the outline opens one thread, the other bars pinned."

## Phase 3 — the Flows tab and its data change (spec §7–§8)

### Task 10: A check names the changed function that raised it (`related`)

**Files:**
- Modify: `backend/codetortoise/reading.py` (`Check`; `build_checks`' `add`), `backend/codetortoise/causes.py` (`_group`, `change_for`, `build_causes`), `frontend/src/reading/types.ts` (`Check`)
- Test: `backend/tests/test_reading.py`, `backend/tests/test_web.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - Backend: `Check.related: str | None = None` — the node id (`N<digits>`) of the changed function that raised the row; sent by `/api/reviews/{id}/reading` and inside every story's `reading.checks`, stored with the reading. It replaces the excluded field `Check.cause_fn` (same value). A reading stored before it validates with `related = None`.
  - Frontend: `Check.related?: string | null` in `src/reading/types.ts`. Task 11 matches it against `BoardFlow.cause`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_reading.py`, in `test_two_kinds_at_one_place_stay_two_rows_each_knowing_what_raised_it`, replace

```python
    assert [(k.cause_fn, k.cause_subject) for k in open_] == [("N1", ""), ("N1", "-2")]
    assert "also" not in open_[0].model_dump() and "cause_fn" not in open_[0].model_dump()
```

with

```python
    assert [(k.related, k.cause_subject) for k in open_] == [("N1", ""), ("N1", "-2")]
    dump = open_[0].model_dump()
    assert "also" not in dump and "cause_subject" not in dump and dump["related"] == "N1"   # sent: it ties a flow to its places
```

and in `test_each_kind_records_the_subject_that_makes_two_rows_one_cause`, replace

```python
    assert {(k.kind, k.cause_fn, k.cause_subject) for k in open_} == {
```

with

```python
    assert {(k.kind, k.related, k.cause_subject) for k in open_} == {
```

In `backend/tests/test_web.py`, add after `test_a_reading_stored_before_causes_is_served_without_causes_not_with_none_to_check`:

```python
def test_checks_name_the_changed_function_that_raised_them_and_a_reading_stored_before_still_serves(env):
    svc, app, _ = env
    owner, rid = _review(app)
    checks = owner.get(f"/api/reviews/{rid}/reading").json()["checks"]
    caller = next(k for k in checks if k["kind"] == "caller")
    assert caller["related"] and caller["related"].startswith("N")         # a node id, never shown, matched to a flow
    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()["reading"]
    assert s1["checks"] and all("related" in k for k in s1["checks"])
    old = svc.store.get_blob(rid, "reading")                               # a reading stored before `related`
    for k in old["checks"]:
        del k["related"]
    svc.store.put_blob(rid, "reading", old)
    r = owner.get(f"/api/reviews/{rid}/reading")
    assert r.status_code == 200 and all(k["related"] is None for k in r.json()["checks"])
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd backend && env PYTHONPATH=$PWD .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_reading.py tests/test_web.py -k "two_kinds_at_one_place or records_the_subject or name_the_changed_function"`
Expected: FAIL — `AttributeError: 'Check' object has no attribute 'related'` (test_reading, twice) and `KeyError: 'related'` (test_web).

- [ ] **Step 3: Rename the field and send it**

In `backend/codetortoise/reading.py`, in `class Check`, replace

```python
    cause_fn: str | None = Field(default=None, exclude=True)   # the changed function that raised it (node id)
```

with

```python
    related: str | None = None        # the changed function that raised it (node id): ties a flow to its places
                                      # (spec 2026-10-25-review-ui-redesign §8); none on a reading stored before it
```

and in `build_checks`' `add`, replace

```python
                          source_line=_source(x, path, line, read_text), cause_fn=related, **kw))
```

with

```python
                          source_line=_source(x, path, line, read_text), related=related, **kw))
```

In `backend/codetortoise/causes.py`, rename every `cause_fn` to `related` — six places:

```python
    return k.kind, k.related or "", k.cause_subject
```

```python
    if kind == "target" and lead.related is None:          # a changed header included by another target's files
```

```python
    n = lead.related
```

```python
            fn_id = ",".join(sorted({fn_part(x, k.related) for k in members if k.related}))
```

```python
        fn = x.label(lead.related) if lead.related else ""
        touched = {lead.related} | {k.node for k in members}
```

Then confirm none is left: `grep -rn "cause_fn" backend/codetortoise backend/tests` prints nothing.

- [ ] **Step 4: Run the backend suite and the linter**

Run: `cd backend && env PYTHONPATH=$PWD .venv/bin/python -m pytest -q -p no:cacheprovider tests && .venv/bin/ruff check codetortoise tests`
Expected: PASS, and `All checks passed!`.

- [ ] **Step 5: Give the frontend type the field**

In `frontend/src/reading/types.ts`, in `interface Check`, replace

```ts
  /** A reader row's field (the owner may mark it a shared sink). */
  field?: string | null;
}
```

with

```ts
  /** A reader row's field (the owner may mark it a shared sink). */
  field?: string | null;
  /** The changed function that raised it, a node id (spec 2026-10-25-review-ui-redesign §8): a flow's places are the
   * checks its `cause` raised at its landing. Absent on a reading stored before it. */
  related?: string | null;
}
```

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/reading.py backend/codetortoise/causes.py backend/tests/test_reading.py backend/tests/test_web.py frontend/src/reading/types.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): a check sends the changed function that raised it, so a flow can find its places

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 11: The Flows tab's rules — groups, titles, lines, sentences, places, causes

**Files:**
- Create: `frontend/src/reading/flowGroups.ts`
- Test: `frontend/src/reading/flowGroups.test.ts`

**Interfaces:**
- Consumes: `BoardFlow` (`src/board/types.ts`: `id`, `path`, `tag`, `lands`, `findings`, `text`, `title`, `cause?`), `Check.related` (Task 10), `Cause`, `CheckKind`, `Mark` (`src/reading/types.ts`), `placeOpen(key, marks)` (`src/reading/causes.ts`).
- Produces (all exported from `src/reading/flowGroups.ts`; `Label = (id: string) => string` turns a node id into its name):
  - `FOLD_AT = 8`
  - `type GroupKind = "field" | "writer" | "function"`; `interface FlowRow { flow: BoardFlow; n: number }` (`n`: 1-based position in the story's flow list, as `flow=N`); `interface FlowGroup { key: string; kind: GroupKind; node: string; rows: FlowRow[] }` (`key` = `` `${kind}:${node}` ``)
  - `changedOf(f): string` — `f.cause`, else the last node of a contract path, else `""`
  - `fieldOf(f): string | null` — a state flow's field node
  - `flowGroups(flows: BoardFlow[]): FlowGroup[]`
  - `someNames(names: string[], max = 3): string`; `tail(text: string): string`
  - `groupTitle(g, label): string`; `groupLine(g, label, open: number): string`; `groupShort(g, label): string`; `rowSentence(f, label): string` — all with names in backticks (render them with `Ticks`; strip backticks for accessible names)
  - `flowPlaces(f, checks: Check[], hidden: ReadonlySet<CheckKind>, label): Check[]`; `placesOf(flows, checks, hidden, label): Map<string, Check[]>` (by flow id)
  - `openKeys(places: Check[], marks: Record<string, Mark>): string[]`; `openFlows(g, places: Map<string, Check[]>, marks): number`
  - `groupCauses(groups, causes: Cause[], checks: Check[], label): { byGroup: Map<string, Cause[]>; rest: Cause[] }` — `causes` must already be the shown ones.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/reading/flowGroups.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { BoardFlow } from "../board/types";
import { changedOf, fieldOf, flowGroups, flowPlaces, groupCauses, groupLine, groupShort, groupTitle, openFlows, openKeys, placesOf,
         rowSentence, someNames, tail } from "./flowGroups";
import type { Cause, Check, CheckKind, Mark } from "./types";

const NAMES: Record<string, string> = {
  N1: "main", N2: "logger_flush", N3: "uart_send", N4: "Uart::errors", N5: "uart_errors", N6: "uart_init", N7: "hal_write",
  N8: "logger_write", N9: "uart_stats",
};
const label = (n: string) => NAMES[n] ?? "a function";

/** A flow as `board.py` `build_flows` makes it: a contract path ends at its change, a state path at its reader. */
function flow(id: string, tag: "state" | "contract", path: string[], cause: string | null | undefined, text: string, title: string,
              findings: string[] = []): BoardFlow {
  return { id, path, tag, lands: tag === "state" ? path[path.length - 1] : path[path.length - 2], fx_at: null, severity: "medium",
           findings, text, title, what: "", effect: "", check: "", what_source: "template", cause };
}
const ignored = flow("f1", "contract", ["N1", "N2", "N3"], "N3", "main → logger_flush → uart_send ⟶ -2 ignored", "logger_flush ignores -2", ["F2"]);
const reads = flow("f2", "state", ["N1", "N3", "N4", "N5"], "N3", "main → uart_send → Uart::errors → uart_errors",
                   "uart_errors sees a new writer of Uart::errors");
const unhandled = flow("f3", "contract", ["N1", "N8", "N3"], "N3", "main → logger_write → uart_send ⟶ -2 unhandled",
                       "logger_write doesn't handle -2");
const blind = flow("f4", "state", ["N1", "N3", "N5"], "N3", "main → uart_send → uart_errors", "uart_errors sees a new writer of the field");
const sig = flow("f5", "contract", ["N1", "N6", "N7"], "N7", "main → uart_init → hal_write ⟶ signature changed",
                 "uart_init calls hal_write (signature changed)");

function check(key: string, kind: CheckKind, node: string, related: string | null | undefined, field: string | null = null): Check {
  const k: Check = { key, kind, story: "S1", thread: "T1", path: "a.c", depot: null, line: 1, function: label(node), node,
                     text: key, source_line: "", finding: null, cites: [], cause: `c-${key}`, field };
  if (related !== undefined) k.related = related;
  return k;
}
/** The same checks as a reading stored before `related` has them (Review Focus 1). */
const stored = (ks: Check[]) => ks.map((k) => check(k.key, k.kind, k.node!, undefined, k.field ?? null));
const cause = (id: string, kind: CheckKind, places: string[], flows: string[] = [], finding: string | null = null): Cause =>
  ({ id, kind, thread: "T1", story: "S1", text: id, places, flows, finding, change: null });
const mark = (key: string, changed = false): Mark => ({ key, user: "ana", at: "", source_line: "", changed });
const none = new Set<CheckKind>();

describe("a flow's field and change", () => {
  it("finds a state flow's field before its reader, never its writer, and none on a contract flow", () => {
    expect(fieldOf(reads)).toBe("N4");
    expect(fieldOf(blind)).toBeNull();                        // the node before the reader is the writer itself
    expect(fieldOf(ignored)).toBeNull();
    expect(fieldOf({ ...reads, path: ["N5"] })).toBeNull();
    expect(fieldOf({ ...reads, cause: null })).toBeNull();    // without its writer the field cannot be told apart
  });

  it("takes a flow's change from its cause, else from the end of a contract path", () => {
    expect(changedOf(reads)).toBe("N3");
    expect(changedOf({ ...sig, cause: undefined })).toBe("N7");
  });
});

describe("flowGroups", () => {
  it("groups state flows by field (else writer) and contract flows by changed function, in the order of their first flow", () => {
    const g = flowGroups([ignored, reads, unhandled, blind, sig]);
    expect(g.map((x) => [x.key, x.kind, x.node, x.rows.map((r) => r.n)])).toEqual([
      ["function:N3", "function", "N3", [1, 3]], ["field:N4", "field", "N4", [2]], ["writer:N3", "writer", "N3", [4]],
      ["function:N7", "function", "N7", [5]]]);
    expect(g[0].rows.map((r) => r.flow.id)).toEqual(["f1", "f3"]);
  });

  it("makes no group of no flows", () => expect(flowGroups([])).toEqual([]));
});

describe("a group's title, line and outline line", () => {
  const [fn, field, writer, hal] = flowGroups([ignored, reads, unhandled, blind, sig]);

  it("says what changed", () => {
    expect(groupTitle(fn, label)).toBe("`uart_send` returns new values");
    expect(groupTitle(field, label)).toBe("`Uart::errors` gets a new writer: `uart_send`");
    expect(groupTitle(writer, label)).toBe("New writes by `uart_send`");
    expect(groupTitle(hal, label)).toBe("`hal_write`'s signature changed");
    const [mixed] = flowGroups([sig, flow("f6", "contract", ["N1", "N8", "N7"], "N7", "main → logger_write → hal_write ⟶ -2 ignored",
                                          "logger_write ignores -2")]);
    expect(groupTitle(mixed, label)).toBe("`hal_write` changed");
  });

  it("names a field's writers once each, in order, the rest as a count", () => {
    const more: Record<string, string> = { W1: "stats_a1", W2: "stats_a2", W3: "stats_a3", W4: "stats_b1", W5: "stats_b2" };
    const lab = (n: string) => more[n] ?? label(n);
    const by = (id: string, w: string) => flow(id, "state", ["N1", w, "N4", "N5"], w, id, "");
    const [two] = flowGroups([by("a", "W4"), by("b", "W5"), by("c", "W4")]);
    expect(groupTitle(two, lab)).toBe("`Uart::errors` gets new writers: `stats_b1`, `stats_b2`");
    const [five] = flowGroups(["W1", "W2", "W3", "W4", "W5"].map((w) => by(w, w)));
    expect(groupTitle(five, lab)).toBe("`Uart::errors` gets new writers: `stats_a1`, `stats_a2`, `stats_a3` and 2 more");
  });

  it("says who reads or calls, how many flows, and how many are open only when some are", () => {
    expect(groupLine(fn, label, 1)).toBe("called by `logger_flush`, `logger_write` · 2 flows · 1 open");
    expect(groupLine(field, label, 0)).toBe("read by `uart_errors` · 1 flow");
    expect(groupLine(writer, label, 1)).toBe("read by `uart_errors` · 1 flow · 1 open");
    expect(someNames(["a", "b", "a", "c", "d", "e"])).toBe("`a`, `b`, `c` and 2 more");
    expect(someNames(["a"])).toBe("`a`");
  });

  it("names a group in the outline by its field, its writer's writes or its function", () => {
    expect([fn, field, writer].map((g) => groupShort(g, label))).toEqual(["`uart_send`", "`Uart::errors`", "`uart_send`'s writes"]);
  });

  it("reads a contract flow's ending after its last arrow", () => {
    expect(tail(sig.text)).toBe("signature changed");
    expect(tail("a → b")).toBe("");
  });
});

describe("rowSentence", () => {
  it("tells a state flow by reader, field and writer, a contract flow by its title with the landing in code style", () => {
    expect(rowSentence(reads, label)).toBe("`uart_errors` sees a new writer of `Uart::errors` · via `uart_send`");
    expect(rowSentence(blind, label)).toBe("`uart_errors` sees new writes by `uart_send`");
    expect(rowSentence(ignored, label)).toBe("`logger_flush` ignores -2");
    expect(rowSentence({ ...ignored, title: "something else" }, label)).toBe("something else");
  });
});

describe("a flow's places", () => {
  const checks = [
    check("result|flush", "result", "N2", "N3"), check("caller|flush", "caller", "N2", "N3"),
    check("reader|errors", "reader", "N5", "N3", "Uart::errors"), check("reader|state", "reader", "N5", "N3", "Uart::state"),
    check("confirm|flush", "confirm", "N2", "N3"), check("result|init", "result", "N6", "N7"),
  ];

  it("are the checks its change raised at its landing, of a kind it asks about", () => {
    expect(flowPlaces(ignored, checks, none, label).map((k) => k.key)).toEqual(["result|flush", "caller|flush"]);
    expect(flowPlaces(reads, checks, none, label).map((k) => k.key)).toEqual(["reader|errors"]);
    expect(flowPlaces(blind, checks, none, label).map((k) => k.key)).toEqual(["reader|errors", "reader|state"]);
    expect(flowPlaces(unhandled, checks, none, label)).toEqual([]);
  });

  it("leave hidden kinds out", () => {
    expect(flowPlaces(ignored, checks, new Set<CheckKind>(["result"]), label).map((k) => k.key)).toEqual(["caller|flush"]);
  });

  it("are none on a reading stored before checks named their change, or for a flow without one (Review Focus 1)", () => {
    expect([ignored, reads, blind].map((f) => flowPlaces(f, stored(checks), none, label))).toEqual([[], [], []]);
    expect(flowPlaces({ ...ignored, cause: null }, checks, none, label)).toEqual([]);
  });

  it("keep a flow open while any is unmarked or its line changed since", () => {
    const places = placesOf([ignored, reads], checks, none, label), [g] = flowGroups([ignored]);
    expect(openKeys(places.get("f1")!, { "result|flush": mark("result|flush") })).toEqual(["caller|flush"]);
    expect(openFlows(g, places, { "result|flush": mark("result|flush"), "caller|flush": mark("caller|flush") })).toBe(0);
    expect(openFlows(g, places, { "result|flush": mark("result|flush"), "caller|flush": mark("caller|flush", true) })).toBe(1);
  });
});

describe("groupCauses", () => {
  const groups = flowGroups([ignored, reads, unhandled, sig]);
  const checks = [
    check("result|flush", "result", "N2", "N3"), check("reader|errors", "reader", "N5", "N3", "Uart::errors"),
    check("caller|init", "caller", "N6", "N7"), check("target|stats", "target", "N9", "N9"), check("untested|s1", "untested", "N3", null),
    check("reader|state", "reader", "N5", "N3", "Uart::state"),
  ];
  const causes = [
    cause("result", "result", ["result|flush"], ["f1", "f2"]), cause("reader", "reader", ["reader|errors"], ["f1", "f2"]),
    cause("hazard", "hazard", [], ["f1"], "F2"), cause("caller", "caller", ["caller|init"], ["f5"]),
    cause("target", "target", ["target|stats"]), cause("untested", "untested", ["untested|s1"]),
    cause("state", "reader", ["reader|state"], ["f2"]),
  ];
  const ids = (m: Map<string, Cause[]>) => [...m].map(([k, cs]) => [k, cs.map((c) => c.id)]);

  it("puts a reader with its field, a caller's kinds with their function, a hazard with its finding's flow, the rest last", () => {
    const { byGroup, rest } = groupCauses(groups, causes, checks, label);
    expect(ids(byGroup)).toEqual([["function:N3", ["result", "hazard"]], ["field:N4", ["reader"]], ["function:N7", ["caller"]]]);
    expect(rest.map((c) => c.id)).toEqual(["target", "untested", "state"]);
  });

  it("falls back to the group holding a cause's first flow on a reading stored before `related` (Review Focus 1)", () => {
    const { byGroup, rest } = groupCauses(groups, [...causes, cause("lost", "caller", [], [])], stored(checks), label);
    expect(ids(byGroup)).toEqual([["function:N3", ["result", "hazard"]], ["field:N4", ["reader"]], ["function:N7", ["caller"]]]);
    expect(rest.map((c) => c.id)).toEqual(["target", "untested", "state", "lost"]);
  });
});
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npx vitest run src/reading/flowGroups.test.ts`
Expected: FAIL — `Failed to resolve import "./flowGroups"`.

- [ ] **Step 3: Write the rules**

Create `frontend/src/reading/flowGroups.ts`:

```ts
/** A story's Flows tab (spec 2026-10-25-review-ui-redesign §7): its flows grouped by what changed, each group's title,
 * line and causes, each flow's one-line sentence and the checks it asks about. Pure, so the rules are tested apart from
 * React. Names come back in backticks, for `Ticks`. */
import type { BoardFlow } from "../board/types";
import { placeOpen } from "./causes";
import type { Cause, Check, CheckKind, Mark } from "./types";

export type Label = (id: string) => string;
export type GroupKind = "field" | "writer" | "function";
/** A flow and its 1-based position in the story's list (as `flow=N` addresses and the Graph tab number it). */
export interface FlowRow { flow: BoardFlow; n: number }
/** `node`: the field, the writer or the changed function; rows in the story's order. */
export interface FlowGroup { key: string; kind: GroupKind; node: string; rows: FlowRow[] }

/** A group shows this many rows before `Show N more` (§7.3). */
export const FOLD_AT = 8;
const CONTRACT_KINDS: readonly CheckKind[] = ["caller", "result", "target", "unanalysed"];
const code = (s: string) => `\`${s}\``;
const flowsWord = (n: number) => `${n} flow${n === 1 ? "" : "s"}`;

/** The changed function a flow comes from: its `cause` (every flow of a story with a reading names it); a contract
 * path ends at it. */
export function changedOf(f: Pick<BoardFlow, "tag" | "path" | "cause">): string {
  return f.cause ?? (f.tag === "contract" ? f.path[f.path.length - 1] : "");
}

/** A state flow's field (§7.1): the node before its landing, when that node is not the writer (`board.py`
 * `build_flows` puts the field there); null for a contract flow or a state flow without one. */
export function fieldOf(f: Pick<BoardFlow, "tag" | "path" | "cause">): string | null {
  if (f.tag !== "state" || f.path.length < 2 || !f.cause) return null;
  const n = f.path[f.path.length - 2];
  return n === f.cause ? null : n;
}

/** The story's flows grouped (§7.1): a state flow by its field, else its writer; a contract flow by its changed
 * function. Groups in the order of their first flow. */
export function flowGroups(flows: BoardFlow[]): FlowGroup[] {
  const out: FlowGroup[] = [], byKey = new Map<string, FlowGroup>();
  flows.forEach((flow, i) => {
    const field = fieldOf(flow);
    const kind: GroupKind = flow.tag === "contract" ? "function" : field ? "field" : "writer";
    const node = field ?? changedOf(flow), key = `${kind}:${node}`;
    let g = byKey.get(key);
    if (!g) {
      g = { key, kind, node, rows: [] };
      byKey.set(key, g);
      out.push(g);
    }
    g.rows.push({ flow, n: i + 1 });
  });
  return out;
}

/** Names in code style, each once, in order; past `max`, "and N more" (§7.2). */
export function someNames(names: string[], max = 3): string {
  const u = [...new Set(names)], head = u.slice(0, max).map(code).join(", ");
  return u.length > max ? `${head} and ${u.length - max} more` : head;
}

/** A contract flow's ending, after the last ⟶ of its text: "signature changed", "-2 ignored", "-2 unhandled". */
export function tail(text: string): string {
  const i = text.lastIndexOf("⟶ ");
  return i < 0 ? "" : text.slice(i + 2);
}

/** A group's title (§7.2). */
export function groupTitle(g: FlowGroup, label: Label): string {
  const name = code(label(g.node));
  if (g.kind === "field") {
    const writers = [...new Set(g.rows.map((r) => label(changedOf(r.flow))))];
    return writers.length === 1 ? `${name} gets a new writer: ${code(writers[0])}` : `${name} gets new writers: ${someNames(writers)}`;
  }
  if (g.kind === "writer") return `New writes by ${name}`;
  const ends = g.rows.map((r) => tail(r.flow.text));
  if (ends.every((e) => e === "signature changed")) return `${name}'s signature changed`;
  if (ends.every((e) => e.endsWith(" ignored") || e.endsWith(" unhandled"))) return `${name} returns new values`;
  return `${name} changed`;
}

/** The line under a group's title (§7.2): who reads or calls, how many flows, and how many still have a place open. */
export function groupLine(g: FlowGroup, label: Label, open: number): string {
  const who = someNames(g.rows.map((r) => label(r.flow.lands)));
  return `${g.kind === "function" ? "called by" : "read by"} ${who} · ${flowsWord(g.rows.length)}${open ? ` · ${open} open` : ""}`;
}

/** A group's line in the outline (§7.6): its field, its writer's writes or its function. */
export function groupShort(g: FlowGroup, label: Label): string {
  return g.kind === "writer" ? `${code(label(g.node))}'s writes` : code(label(g.node));
}

/** A row's one line (§7.3): a state flow's reader, field and writer; a contract flow's title, its landing in code style. */
export function rowSentence(f: BoardFlow, label: Label): string {
  const reader = code(label(f.lands));
  if (f.tag === "state") {
    const field = fieldOf(f), writer = code(label(changedOf(f)));
    return field ? `${reader} sees a new writer of ${code(label(field))} · via ${writer}` : `${reader} sees new writes by ${writer}`;
  }
  const l = label(f.lands);
  return f.title.startsWith(l) ? `${reader}${f.title.slice(l.length)}` : f.title;
}

/** The checks a flow asks about (§7.5), hidden kinds left out: those its change raised at its landing — a reader of its
 * field, or a caller's, result's, target's or unanalysed row. None on a reading stored before `related`. */
export function flowPlaces(f: BoardFlow, checks: Check[], hidden: ReadonlySet<CheckKind>, label: Label): Check[] {
  if (!f.cause) return [];
  const field = fieldOf(f), name = field ? label(field) : null;
  return checks.filter((k) => !hidden.has(k.kind) && !!k.related && k.related === f.cause && k.node === f.lands
    && (f.tag === "state" ? k.kind === "reader" && (name === null || k.field === name) : CONTRACT_KINDS.includes(k.kind)));
}

/** Every flow's places, by flow id. */
export function placesOf(flows: BoardFlow[], checks: Check[], hidden: ReadonlySet<CheckKind>, label: Label): Map<string, Check[]> {
  return new Map(flows.map((f) => [f.id, flowPlaces(f, checks, hidden, label)]));
}

/** The keys of a flow's places still open. */
export function openKeys(places: Check[], marks: Record<string, Mark>): string[] {
  return places.filter((k) => placeOpen(k.key, marks)).map((k) => k.key);
}

/** How many of a group's flows have a place still open. */
export function openFlows(g: FlowGroup, places: Map<string, Check[]>, marks: Record<string, Mark>): number {
  return g.rows.filter((r) => openKeys(places.get(r.flow.id) ?? [], marks).length > 0).length;
}

/** The story's shown causes between its groups and the end line (§7.4), each keeping its order: a reader with its
 * field's group, a caller's kinds with their function's (on a reading stored before `related`, with the group holding
 * the cause's first flow), a hazard or confirm with the group of its finding's flow; the rest at the end. */
export function groupCauses(groups: FlowGroup[], causes: Cause[], checks: Check[], label: Label): { byGroup: Map<string, Cause[]>; rest: Cause[] } {
  const byKey = new Map(checks.map((k) => [k.key, k]));
  const holding = (id: string) => groups.find((g) => g.rows.some((r) => r.flow.id === id));
  const byGroup = new Map<string, Cause[]>(), rest: Cause[] = [];
  for (const c of causes) {
    const ks = c.places.flatMap((p) => byKey.get(p) ?? []), finding = c.finding;
    let g: FlowGroup | undefined;
    if (c.kind === "reader") {
      const fields = new Set(ks.map((k) => k.field));
      g = groups.find((x) => x.kind === "field" && fields.has(label(x.node)));
    } else if (CONTRACT_KINDS.includes(c.kind)) {
      const related = ks.find((k) => k.related)?.related;
      g = related ? groups.find((x) => x.kind === "function" && x.node === related) : c.flows.length ? holding(c.flows[0]) : undefined;
    } else if ((c.kind === "hazard" || c.kind === "confirm") && finding) {
      g = groups.find((x) => x.rows.some((r) => r.flow.findings.includes(finding)));
    }
    if (g) byGroup.set(g.key, [...(byGroup.get(g.key) ?? []), c]);
    else rest.push(c);
  }
  return { byGroup, rest };
}
```

- [ ] **Step 4: Run them to watch them pass**

Run: `cd frontend && npx vitest run src/reading/flowGroups.test.ts && npx tsc --noEmit`
Expected: PASS (16 tests), and tsc prints nothing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/reading/flowGroups.ts frontend/src/reading/flowGroups.test.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): group a story's flows by what changed and find each flow's places

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 12: The Flows tab shows groups of one-line rows that open in place and tick

**Files:**
- Create: `frontend/src/workspace/Chips.tsx` (moved out of `StoryTabs.tsx`), `frontend/src/workspace/FlowsTab.tsx`, `frontend/e2e/flow-groups.spec.ts`
- Modify: `frontend/src/workspace/StoryTabs.tsx` (imports; `bare`, `Chips` and `Flows` go; `StoryTabs` renders `FlowsTab`), `frontend/src/workspace/workspace.css` (`.st-flow*` rules become `.fl-*` rules)
- Test: `frontend/e2e/flow-groups.spec.ts`; the specs that read today's flow cards: `frontend/e2e/workspace-reading.spec.ts`, `frontend/e2e/outline-causes.spec.ts`, `frontend/e2e/workspace-tier1.spec.ts`, `frontend/e2e/workspace-story.spec.ts`, `frontend/e2e/ai.spec.ts`

**Interfaces:**
- Consumes: everything Task 11 exports from `src/reading/flowGroups.ts`; `Check.related` (Task 10); `AiText` (Task 1); `flowPart(parts, f)` (`src/reading/story.ts`); `shown` (`src/reading/causes.ts`); `api.markChecks(id, keys)`, `api.unmarkCheck(id, key)`; `d.loadReading()`, `d.loadTicks()` (`useWs().data`).
- Produces:
  - `export default function Chips({ causes }: { causes: Cause[] })` in `src/workspace/Chips.tsx` — unchanged behaviour (`ul.st-chips` of `a.st-chip.<kind>[.done]`, `aria-label="Open check: <line>"`).
  - `export default function FlowsTab({ detail, sr, flows }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[] })`, rendered by `StoryTabs` with `key={st.id}`. DOM: per group `section.fl-group[aria-label=<title without backticks>]` > `h3`, `p.fl-line`, `ul.st-chips` (its causes), `ol.fl-rows` > `li.fl-row#flow-<n>` (`.on` when open) > `div.fl-head` > [`input.fl-tick[type=checkbox][aria-label="Looks fine: <sentence>"]` when the flow has places] + `button.fl-toggle[aria-expanded][aria-label="Flow <n>: <sentence>"]` (`span.fl-n`, `span.fl-one`); the open row's `div.fl-body[role=region][aria-label="Flow <n>: <sentence>"]` > `p.fl-path` (field in `mark`), the account or `what` (`AiText`), `p.fl-check`, chips when the flow has no places, `div.fl-acts` (`Looks fine`, `Reopen`, `Next flow ›`); `button.link.fl-more` `Show N more`; then `section.fl-also[aria-label="Also in this story"]`, the effects section, or `No flows in this story.` One row is open at a time. Task 13 adds keys to this component; Task 14 links the outline to `flow=N`.

- [ ] **Step 1: Write the failing e2e tests**

Create `frontend/e2e/flow-groups.spec.ts`:

```ts
import { devices, expect, test, type APIResponse, type Locator, type Page, type Route } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

const FOUR = "101 102 103 104";

/** A reading stored before checks named the changed function that raised them (Review Focus 1). */
async function withoutRelated(page: Page) {
  const strip = async (route: Route) => {
    let res: APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    const r = j.reading ?? j;
    for (const k of [...r?.checks ?? [], ...r?.cleared ?? []]) delete k.related;
    await route.fulfill({ response: res, json: j });
  };
  await page.route("**/api/reviews/*/reading", strip);
  await page.route("**/api/reviews/*/stories/*", strip);
}

/** Each element's attribute `name`, in order. */
const labels = (l: Locator, name = "aria-label") => l.evaluateAll((els, a) => els.map((e) => e.getAttribute(a)), name);

test.describe("the Flows tab", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("flows come in groups by what changed, a line each; a row opens in place and its box marks its places fine", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const groups = page.locator("section.fl-group");
    await expect(groups).toHaveCount(2);
    expect(await labels(groups)).toEqual(["uart_send returns new values", "Uart::errors gets a new writer: uart_send"]);
    await expect(groups.locator(".fl-line")).toHaveText(["called by logger_flush · 1 flow · 1 open", "read by uart_errors · 1 flow · 1 open"]);
    await expect(groups.nth(0).locator(":scope > .st-chips .st-chip"))
      .toHaveText(["logger_flush ignores the result of uart_send, which can now return -2"]);
    await expect(groups.nth(1).locator(":scope > .st-chips .st-chip")).toHaveText(["uart_errors reads Uart::errors, which uart_send now writes"]);
    const toggles = page.locator(".fl-toggle");
    expect(await labels(toggles)).toEqual(["Flow 1: logger_flush ignores -2",
                                           "Flow 2: uart_errors sees a new writer of Uart::errors · via uart_send"]);
    expect(await labels(toggles, "aria-expanded")).toEqual(["false", "false"]);
    await toggles.nth(0).click();
    await page.getByRole("region", { name: /^Flow 1: / }).getByRole("button", { name: "Next flow ›" }).click();
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "false");
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "true");
    const card = page.getByRole("region", { name: /^Flow 2: / });
    await expect(card.locator(".fl-path")).toContainText("uart_send → Uart::errors → uart_errors");
    await expect(card.locator(".fl-path mark")).toHaveText("Uart::errors");
    await expect(card.locator(".fl-check")).toHaveText("Check whether uart_errors assumes Uart::errors only changes the way it did before");
    await card.getByRole("button", { name: "Looks fine" }).click();
    const tick = page.getByRole("checkbox", { name: "Looks fine: uart_errors sees a new writer of Uart::errors · via uart_send" });
    await expect(tick).toBeChecked();
    await expect(groups.nth(1).locator(".fl-line")).toHaveText("read by uart_errors · 1 flow");
    await expect(groups.nth(1).locator(".st-chip.done")).toHaveCount(1);             // its one place was the check's only place
    await tick.click();                                                              // unticking reopens it
    await expect(tick).not.toBeChecked();
    await expect(card.getByRole("button", { name: "Looks fine" })).toBeVisible();
    await page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" }).click();
    await expect(groups.nth(0).locator(".fl-line")).toHaveText("called by logger_flush · 1 flow");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("a reading stored before checks named their change shows no tick box and keeps every chip (Review Focus 1)", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await withoutRelated(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const groups = page.locator("section.fl-group");
    await expect(page.locator(".fl-row")).toHaveCount(2);
    await expect(page.locator(".fl-tick")).toHaveCount(0);
    await expect(groups.locator(".fl-line")).toHaveText(["called by logger_flush · 1 flow", "read by uart_errors · 1 flow"]);
    await expect(groups.nth(0).locator(":scope > .st-chips .st-chip"))
      .toHaveText(["logger_flush ignores the result of uart_send, which can now return -2"]);
    await expect(groups.nth(1).locator(":scope > .st-chips .st-chip")).toHaveText(["uart_errors reads Uart::errors, which uart_send now writes"]);
    await page.locator(".fl-toggle").first().click();
    const card = page.getByRole("region", { name: /^Flow 1: / });
    await expect(card.locator(".st-chip")).toHaveText(["logger_flush ignores the result of uart_send, which can now return -2",
      "uart_errors reads Uart::errors, which uart_send now writes"]);              // a flow without places shows its causes
    await expect(card.getByRole("button", { name: "Looks fine" })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test.describe("a story with many flows", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("each group shows eight rows until Show N more; a flow=N address unfolds its group and opens its row", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const groups = page.locator("section.fl-group");
    await expect(groups).toHaveCount(6);                                             // 140 flows
    await expect(groups.first()).toHaveAttribute("aria-label", "TelemDev::errors gets new writers: telem_a1, telem_a2, telem_a3 and 2 more");
    await expect(groups.first().locator(".fl-line")).toHaveText("read by telem_d1, telem_d2, telem_d3 and 2 more · 25 flows · 25 open");
    await expect(page.locator(".fl-row")).toHaveCount(48);
    expect((await page.locator(".fl-more").allTextContents()).sort())
      .toEqual(["Show 17 more", "Show 17 more", "Show 17 more", "Show 17 more", "Show 17 more", "Show 7 more"]);
    await groups.first().getByRole("button", { name: "Show 17 more" }).click();
    await expect(groups.first().locator(".fl-row")).toHaveCount(25);
    await expect(page.locator(".fl-more")).toHaveCount(5);
    await expect(page.getByRole("region", { name: "Also in this story" })
      .getByRole("link", { name: "Open check: 26 functions no test calls" })).toBeVisible();
    await page.goto(`${base}/s/S1?flow=60`);                                         // the tenth row of UartDev::errors: folded
    await expect(page.getByRole("region", { name: /^UartDev::errors gets new writers: / }).locator(".fl-row")).toHaveCount(25);
    await expect(page.locator("#flow-60 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("region", { name: /^Flow 60: / })).toBeInViewport();
    await expectNoNodeIds(page);
  });
});

test.describe("the Flows tab on a phone", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("rows stay one line and nothing scrolls sideways, closed or open", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".fl-row").first()).toBeVisible();
    const wrapped = () => page.locator(".fl-one").evaluateAll((els) => els.filter((e) =>
      e.getBoundingClientRect().height > 1.5 * parseFloat(getComputedStyle(e).lineHeight)).length);
    expect(await wrapped()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await page.locator(".fl-toggle").first().click();
    await expect(page.getByRole("region", { name: /^Flow 1: / })).toBeVisible();
    expect(await wrapped()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

Then point the specs that read today's flow cards at the groups and rows:

- `frontend/e2e/workspace-reading.spec.ts` — replace
  ```ts
      const chips = page.getByRole("region", { name: /^Flow 1: / }).locator(".st-chip");      // the checks on its flow, Confirm hidden
  ```
  with
  ```ts
      const chips = page.getByRole("region", { name: "hal_write's signature changed" }).locator(".st-chip");   // its group's checks, Confirm hidden
  ```
  and replace
  ```ts
      await expect(page.getByRole("region", { name: /^Flow 1: / }).locator(".st-chip")).toHaveText([
        "logger_flush ignores the result of uart_send, which can now return -2", "uart_errors reads Uart::errors, which uart_send now writes"]);
  ```
  with
  ```ts
      await expect(page.getByRole("region", { name: "uart_send returns new values" }).locator(".st-chip"))
        .toHaveText(["logger_flush ignores the result of uart_send, which can now return -2"]);
      await expect(page.getByRole("region", { name: "Uart::errors gets a new writer: uart_send" }).locator(".st-chip"))
        .toHaveText(["uart_errors reads Uart::errors, which uart_send now writes"]);
  ```
- `frontend/e2e/outline-causes.spec.ts` — replace
  ```ts
      await page.goto(`${base}/s/S1`);
      const cards = page.getByRole("region", { name: /^Flow \d+:/ });
      await expect(cards.first()).toBeVisible();
  ```
  with
  ```ts
      await page.goto(`${base}/s/S1`);
      await expect(page.locator(".fl-row").first()).toBeVisible();
  ```
  replace
  ```ts
      await expect(page.getByRole("region", { name: /^Flow 1:/ })).toHaveClass(/\blit\b/);
      await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeInViewport();
  ```
  with
  ```ts
      await expect(page.locator("#flow-1 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
      await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeInViewport();
  ```
  replace the whole test `"with every kind hidden a story shows no chips"` with
  ```ts
    test("with every kind hidden a story shows no chips and no tick boxes", async ({ page }) => {
      const base = await startReview(page, FOUR);
      await page.evaluate(() => window.localStorage.setItem("ct.ws.hiddenKinds", JSON.stringify(
        ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"])));
      await page.goto(`${base}/s/S1`);
      await expect(page.locator(".fl-row").first()).toBeVisible();
      await expect(page.locator(".st-chip")).toHaveCount(0);
      await expect(page.locator(".fl-tick")).toHaveCount(0);                     // a hidden kind is no place to tick
      await expect(page.getByRole("region", { name: "Also in this story" })).toHaveCount(0);
    });
  ```
  replace the whole test `"a story stored before causes shows no chips"` with
  ```ts
    test("a story stored before causes shows no chips", async ({ page }) => {
      await withoutCauses(page);
      const base = await startReview(page, FOUR);
      await page.goto(`${base}/s/S1`);
      await expect(page.locator(".fl-row").first()).toBeVisible();
      await expect(page.locator(".st-chip")).toHaveCount(0);
    });
  ```
  replace
  ```ts
    test("a very long check line ends in an ellipsis inside its flow card, the whole line on hover", async ({ page }) => {
  ```
  with
  ```ts
    test("a very long check line ends in an ellipsis inside its group, the whole line on hover", async ({ page }) => {
  ```
  and replace
  ```ts
      await page.goto(`${base}/s/S1`);
      await expect(page.getByRole("region", { name: /^Flow 2:/ })).toContainText("SECOND-FLOW-ACCOUNT");
      await expect(page.getByRole("region", { name: /^Flow 1:/ })).not.toContainText("SECOND-FLOW-ACCOUNT");
  ```
  with
  ```ts
      await page.goto(`${base}/s/S1?flow=2`);
      await expect(page.getByRole("region", { name: /^Flow 2:/ })).toContainText("SECOND-FLOW-ACCOUNT");
      await page.locator("#flow-1 .fl-toggle").click();
      await expect(page.getByRole("region", { name: /^Flow 1:/ })).not.toContainText("SECOND-FLOW-ACCOUNT");
  ```
- `frontend/e2e/workspace-tier1.spec.ts` — replace
  ```ts
      const chip = page.getByRole("region", { name: /^Flow 1: / }).locator(".st-chip").first();   // the hazard leads its flow's checks
  ```
  with
  ```ts
      const chip = page.getByRole("region", { name: "uart_send returns new values" }).locator(".st-chip").first();   // the hazard leads its group's checks
  ```
- `frontend/e2e/workspace-story.spec.ts` — replace
  ```ts
      await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeVisible();      // measure in the Flows layout
  ```
  with
  ```ts
      await expect(page.locator(".fl-row").first()).toBeVisible();                     // measure in the Flows layout
  ```
- `frontend/e2e/ai.spec.ts` — in the test `"a story tells the weak model's account…"`, replace
  ```ts
      const cards = page.getByRole("region", { name: /^Flow \d+: / });
      expect(await cards.count()).toBeGreaterThan(0);
      await expect(cards.locator("> p.ai-text")).toHaveCount(await cards.count());
      await expect(cards.first()).toContainText("The caller reaches uart_send on this path.");
  ```
  with
  ```ts
      const rows = page.locator(".fl-row");
      expect(await rows.count()).toBeGreaterThan(0);
      await rows.first().locator(".fl-toggle").click();                                // a row opens in place
      const card = page.getByRole("region", { name: /^Flow \d+: / });
      await expect(card.locator("> p.ai-text")).toContainText("The caller reaches uart_send on this path.");
      await expect(card.locator("> p.ai-text")).toHaveAttribute("title", "Written by AI");
  ```

- [ ] **Step 2: Build and run them to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/flow-groups.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-story.spec.ts e2e/ai.spec.ts`
Expected: FAIL — `section.fl-group` count 0 (expected 2 / 6), no `.fl-row`, no region named `uart_send returns new values`.

- [ ] **Step 3: Move the chips into their own file**

Create `frontend/src/workspace/Chips.tsx`:

```tsx
import { Link } from "react-router-dom";
import { causeOpen, firstOpenAt } from "../reading/causes";
import type { Cause } from "../reading/types";
import { useWs } from "./context";
import { Ticks } from "./NameText";
import { plainNames } from "./names";

const bare = (s: string) => s.replaceAll("`", "");

/** Check chips (spec 2026-10-16-outline-and-causes §2.3): one per shown cause, done ones muted with ✓; a chip opens the
 * stepper at the cause's first open place. A Flows group's, a flow's without places, the Flows tab's end line and a
 * story's without flows (spec 2026-10-25-review-ui-redesign §7). */
export default function Chips({ causes }: { causes: Cause[] }) {
  const ws = useWs(), d = ws.data, marks = d.reading?.marks ?? {};
  if (!causes.length) return null;
  return (
    <ul className="st-chips">{causes.map((c) => {
      const line = plainNames(c.text, d.names), done = !causeOpen(c, marks);
      return (
        <li key={c.id}><Link className={`st-chip ${c.kind}${done ? " done" : ""}`} to={ws.link(ws.opened({ cause: c.id, at: firstOpenAt(c, marks) }))}
                             title={bare(line)} aria-label={`Open check: ${bare(line)}`}>{done && <span aria-hidden>✓ </span>}<Ticks text={line} /></Link></li>
      );
    })}</ul>
  );
}
```

- [ ] **Step 4: Build the tab**

Create `frontend/src/workspace/FlowsTab.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import type { BoardFlow, StoryDetail } from "../board/types";
import AiText from "../components/AiText";
import { shown } from "../reading/causes";
import { FOLD_AT, fieldOf, type FlowGroup, flowGroups, groupCauses, groupLine, groupTitle, openFlows, openKeys, placesOf,
         rowSentence } from "../reading/flowGroups";
import { flowPart } from "../reading/story";
import type { StoryReading } from "../reading/types";
import Chips from "./Chips";
import { useWs } from "./context";
import NameText, { Ticks } from "./NameText";

const bare = (s: string) => s.replaceAll("`", "");

/** The Flows tab (spec 2026-10-25-review-ui-redesign §7): the story's flows in groups by what changed, a line each;
 * a row opens in place, and its box marks its places fine for everyone. Then the checks no group takes and what the
 * change means for the rest. One row is open at a time; `flow=N` opens row N and unfolds its group. */
export default function FlowsTab({ detail, sr, flows }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[] }) {
  const ws = useWs(), d = ws.data, lit = ws.addr.flow, marks = d.reading?.marks ?? {};
  const names = new Map(detail.board.nodes.map((n) => [n.id, n.label]));
  const label = (n: string) => names.get(n) ?? d.names[n]?.label ?? "a function";
  const groups = flowGroups(flows), places = placesOf(flows, sr.checks, ws.hidden, label);
  const causes = shown(sr.causes ?? [], ws.hidden), { byGroup, rest } = groupCauses(groups, causes, sr.checks, label);
  const parts = sr.account ?? [], effects = parts.find((p) => p.kind === "effects");
  const [open, setOpen] = useState<number | null>(lit);
  const [more, setMore] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (lit) setOpen(lit); }, [lit]);
  useEffect(() => { if (lit) document.getElementById(`flow-${lit}`)?.scrollIntoView({ block: "start" }); }, [lit]);
  const order = groups.flatMap((g) => g.rows.map((r) => r.n));                  // the rows as they read, group by group
  const run = (act: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    act().then(() => Promise.all([d.loadReading(), d.loadTicks().catch(() => {})]))
      .catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
  };
  const fine = (keys: string[]) => run(() => api.markChecks(d.id, keys));
  const reopen = (keys: string[]) => run(async () => { for (const k of keys) await api.unmarkCheck(d.id, k); });
  // a row an address or Next flow › opens unfolds its group
  const unfolded = (g: FlowGroup) => g.rows.length <= FOLD_AT || more.has(g.key) || g.rows.some((r) => r.n === lit || r.n === open);
  return (
    <div className="st-flows">
      {error && <div className="banner warn">{error}</div>}
      {groups.map((g) => {
        const title = groupTitle(g, label), rows = unfolded(g) ? g.rows : g.rows.slice(0, FOLD_AT);
        return (
          <section key={g.key} className="fl-group" aria-label={bare(title)}>
            <h3><Ticks text={title} /></h3>
            <p className="fl-line"><Ticks text={groupLine(g, label, openFlows(g, places, marks))} /></p>
            <Chips causes={byGroup.get(g.key) ?? []} />
            <ol className="fl-rows">{rows.map(({ flow, n }) => {
              const sentence = rowSentence(flow, label), mine = places.get(flow.id) ?? [], left = openKeys(mine, marks);
              const done = mine.length > 0 && !left.length, on = open === n, part = flowPart(parts, flow), field = fieldOf(flow);
              return (
                <li key={flow.id} id={`flow-${n}`} className={`fl-row${on ? " on" : ""}`}>
                  <div className="fl-head">
                    {mine.length > 0 && <input type="checkbox" className="fl-tick" checked={done} disabled={busy}
                                               aria-label={`Looks fine: ${bare(sentence)}`}
                                               onChange={() => (done ? reopen(mine.map((k) => k.key)) : fine(left))} />}
                    <button className="fl-toggle" aria-expanded={on} title={bare(sentence)} aria-label={`Flow ${n}: ${bare(sentence)}`}
                            onClick={() => setOpen(on ? null : n)}>
                      <span className="fl-n">{n}</span><span className="fl-one"><Ticks text={sentence} /></span>
                    </button>
                  </div>
                  {on && (
                    <div className="fl-body" role="region" aria-label={`Flow ${n}: ${bare(sentence)}`}>
                      <p className="fl-path mono">{flow.path.map((p, i) => (
                        <span key={i}>{i > 0 && " → "}{p === field ? <mark>{label(p)}</mark> : label(p)}</span>
                      ))}</p>
                      {part ? <AiText><NameText text={part.text} /></AiText>
                        : <AiText ai={flow.what_source === "llm"}><NameText text={flow.what} /></AiText>}
                      <p className="fl-check"><NameText text={`Check ${flow.check}`} /></p>
                      {!mine.length && <Chips causes={causes.filter((c) => c.flows.includes(flow.id))} />}
                      <div className="fl-acts">
                        {left.length > 0 && <button onClick={() => fine(left)} disabled={busy}>Looks fine</button>}
                        {done && <button className="link" onClick={() => reopen(mine.map((k) => k.key))} disabled={busy}>Reopen</button>}
                        <button className="link" onClick={() => setOpen(order[order.indexOf(n) + 1] ?? null)}>Next flow ›</button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}</ol>
            {rows.length < g.rows.length && (
              <button className="link fl-more" onClick={() => setMore(new Set([...more, g.key]))}>Show {g.rows.length - rows.length} more</button>
            )}
          </section>
        );
      })}
      {!flows.length && <p className="muted">No flows in this story.</p>}
      {rest.length > 0 && <section className="st-other fl-also" aria-label="Also in this story"><span>Also in this story:</span><Chips causes={rest} /></section>}
      {effects && <section className="st-effects" aria-label={effects.heading}><h3>{effects.heading}</h3>
        <AiText><NameText text={effects.text} /></AiText></section>}
    </div>
  );
}
```

- [ ] **Step 5: Put the tab in the story's tabs**

In `frontend/src/workspace/StoryTabs.tsx`, change the imports:

- replace `import { useEffect, useState } from "react";` with `import { useState } from "react";`
- replace `import { causeOpen, firstOpenAt, shown } from "../reading/causes";` with `import { shown } from "../reading/causes";`
- replace `import { byEntry, codeOrder, flowLabel, flowPart, foldPath, readOrder, rewriteText, storyTabs, type TabSec, type TabSpec, whereByCl, whereTree } from "../reading/story";` with `import { byEntry, codeOrder, foldPath, readOrder, rewriteText, storyTabs, type TabSec, type TabSpec, whereByCl, whereTree } from "../reading/story";`
- replace `import type { CallPath, Cause, ContractRow, StoryReading, WhereFile } from "../reading/types";` with `import type { CallPath, ContractRow, StoryReading, WhereFile } from "../reading/types";`
- replace `import type { Address } from "./address";` with
  ```tsx
  import type { Address } from "./address";
  import Chips from "./Chips";
  ```
- replace `import FunctionCode from "./FunctionCode";` with
  ```tsx
  import FlowsTab from "./FlowsTab";
  import FunctionCode from "./FunctionCode";
  ```
- delete `import { plainNames } from "./names";`

Delete `const bare = (s: string) => s.replaceAll("`", "");`, the whole `Chips` function with its doc comment (`/** A flow card's or the story's check chips (§2.3)…`), and the whole `Flows` function with its doc comment (`/** Flows (§2.3): a numbered card per flow…`). `StoryCauses` stays and now uses the imported `Chips`.

In `StoryTabs`, replace

```tsx
      {active === "flows" && <Flows detail={detail} sr={sr} flows={flows} />}
```

with

```tsx
      {active === "flows" && <FlowsTab key={st.id} detail={detail} sr={sr} flows={flows} />}
```

- [ ] **Step 6: Style the groups and rows**

In `frontend/src/workspace/workspace.css`, replace

```css
.st-flow { border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; scroll-margin-top: 12px; }
.st-flow.lit { border-color: var(--accent); }
.st-flow h3 { margin: 0 0 6px; font-size: 14px; overflow-wrap: anywhere; }
.st-flow-n { display: inline-block; min-width: 1.6em; color: var(--muted); }
```

with

```css
/* the Flows tab (spec 2026-10-25-review-ui-redesign §7): a group per thing that changed, a line per flow */
.fl-group > h3 { margin: 20px 0 6px; font-size: 15px; font-weight: 650; color: var(--ink); overflow-wrap: anywhere; }
.fl-group:first-of-type > h3 { margin-top: 4px; }
.fl-line { margin: 0 0 8px; font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }
.fl-group > .st-chips { margin: 0 0 8px; }
.fl-rows { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--line); }
.fl-row { border-bottom: 1px solid var(--line); scroll-margin-top: 12px; }
.fl-head { display: flex; align-items: center; gap: 6px; min-width: 0; padding-left: 4px; }
.fl-tick { flex: none; margin: 0; }
.fl-toggle { flex: 1; min-width: 0; display: flex; align-items: baseline; gap: 8px; border: 0; border-radius: 0; background: none;
  padding: 6px 4px; font: 400 13.5px/1.4 var(--sans); color: var(--ink); text-align: left; }
.fl-toggle:hover, .fl-toggle:focus-visible { background: var(--gap-bg); }
.fl-row.on .fl-toggle { font-weight: 600; }
.fl-n { flex: none; min-width: 2.2em; text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
.fl-one { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fl-body { padding: 2px 8px 12px 38px; }
.fl-body > p { margin: 0 0 8px; }
.fl-path { font-size: 12.5px; color: var(--muted); overflow-wrap: anywhere; }
.fl-path mark { background: var(--gap-bg); color: var(--ink); border-radius: 3px; padding: 0 2px; }
.fl-acts { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; margin-top: 8px; }
.fl-more { margin: 6px 0 0; }
.fl-also { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; margin: 20px 0 0; }
.fl-also > span { font-weight: 600; }
.fl-also > .st-chips { margin: 0; }
@media (max-width: 640px) { .fl-body { padding-left: 12px; } }
```

- [ ] **Step 7: Build and run the specs to watch them pass**

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && E2E e2e/flow-groups.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-story.spec.ts e2e/ai.spec.ts e2e/long-text.spec.ts e2e/workspace-panels.spec.ts; rm -rf $(git rev-parse --show-toplevel)/.pwtmp`
Expected: PASS. (`long-text.spec` confirms long names in rows end in an ellipsis with their hover; `workspace-panels.spec` opens checks from a story.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/workspace/Chips.tsx frontend/src/workspace/FlowsTab.tsx frontend/src/workspace/StoryTabs.tsx frontend/src/workspace/workspace.css frontend/e2e/flow-groups.spec.ts frontend/e2e/workspace-reading.spec.ts frontend/e2e/outline-causes.spec.ts frontend/e2e/workspace-tier1.spec.ts frontend/e2e/workspace-story.spec.ts frontend/e2e/ai.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): the Flows tab groups flows by what changed into one-line rows that open in place and tick

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 13: J, K, Enter and F step through the Flows tab's rows

**Files:**
- Create: `frontend/src/workspace/keys.ts`
- Modify: `frontend/src/workspace/FlowsTab.tsx` (imports; the row J, K and F act on; the key handler; the toggle's `onFocus`), `frontend/src/workspace/CauseStepper.tsx` (imports `typing` instead of defining it), `frontend/src/workspace/HowToRead.tsx` (the story line)
- Test: `frontend/e2e/flow-groups.spec.ts`, `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: `FlowsTab` (Task 12: `order`, `places`, `marks`, `fine`, `busy`, `open`, `lit`, `FlowGroup`, `openKeys`); `HowToRead` as Task 6 left it; `explainItem(scope, item)` (Task 4, `e2e/helpers.ts`).
- Produces:
  - `export const typing: (t: EventTarget | null) => boolean` in `src/workspace/keys.ts` — true in a text input, a text area, a select or editable text; false on a tick box, a radio or a button. `CauseStepper` and `FlowsTab` use it.
  - On the Flows tab, when no cause is open in the side panel, focus is not in a text field, no mark is on its way and no modifier is held: **J** focuses the next row's toggle (the first when none is current), **K** the previous one, **F** marks the current row's open places fine and focuses the next row (after it, wrapping) that still has open places. Enter is the focused toggle button's own click. A key that reaches a folded row unfolds its group.

- [ ] **Step 1: Write the failing tests**

In `frontend/e2e/flow-groups.spec.ts`, change the helpers import to

```ts
import { expectNamed, expectNoNodeIds, explainItem, startReview } from "./helpers";
```

and add, inside `test.describe("the Flows tab", …)` after its last test:

```ts
  test("J and K move between rows, Enter opens one, F marks its places fine and moves to the next open row", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    await expect(toggles).toHaveCount(2);
    await page.keyboard.press("j");
    await expect(toggles.nth(0)).toBeFocused();
    await page.keyboard.press("j");
    await expect(toggles.nth(1)).toBeFocused();
    await page.keyboard.press("k");
    await expect(toggles.nth(0)).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Enter");
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("f");
    await expect(page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" })).toBeChecked();
    await expect(toggles.nth(1)).toBeFocused();
    const tick = page.getByRole("checkbox", { name: /^Looks fine: uart_errors/ });
    await tick.click();                                                   // a tick box is no text field: K still moves
    await expect(tick).toBeChecked();
    await expect(tick).toBeEnabled();
    await page.keyboard.press("k");
    await expect(toggles.nth(0)).toBeFocused();
  });
```

inside `test.describe("a story with many flows", …)` after its test:

```ts
  test("while a check is open beside the page J, K and F are the stepper's, and letters in its comment box (Review Focus 4)", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const readers = "5 places read UartDev::errors, which uart_a1 now writes";
    await page.getByRole("link", { name: `Open check: ${readers}` }).click();
    const panel = page.getByRole("complementary", { name: `Check: ${readers}` });
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await page.keyboard.press("j");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await page.keyboard.press("f");
    await expect(panel.locator(".cs-pos")).toHaveText("3 / 5");
    await expect(page.getByRole("checkbox", { name: "Looks fine: uart_d2 sees a new writer of UartDev::errors · via uart_a1" })).toBeChecked();
    await expect(page.locator(".fl-toggle:focus")).toHaveCount(0);
    await expect(page.locator(".fl-row.on")).toHaveCount(0);
    await panel.getByRole("button", { name: "Comment" }).click();
    const box = panel.getByPlaceholder("Leave a comment…");
    await box.pressSequentially("jkf");
    await expect(box).toHaveValue("jkf");
    await expect(panel.locator(".cs-pos")).toHaveText("3 / 5");
    await expect(page.locator(".fl-toggle:focus")).toHaveCount(0);
    await panel.getByRole("link", { name: "Close the check" }).click();
    await expect(panel).toHaveCount(0);
    await page.keyboard.press("j");                                       // the panel closed: the keys are the tab's again
    await expect(page.locator(".fl-toggle").first()).toBeFocused();
  });
```

and at the end of the file:

```ts
test.describe("the Flows tab with AI", () => {
  test.use({ baseURL: "http://127.0.0.1:8798", viewport: { width: 1440, height: 900 } });

  test("J, K and F are letters in the story's question box, and move rows again once it loses focus (Review Focus 4)", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".fl-toggle").first()).toBeVisible();
    await explainItem(page.locator(".ws-story-head"), "Ask a question…");
    const box = page.getByRole("textbox", { name: "What should the AI explain?" });
    await box.pressSequentially("jkf");
    await expect(box).toHaveValue("jkf");
    await expect(page.locator(".fl-toggle:focus")).toHaveCount(0);
    await expect(page.locator(".fl-tick:checked")).toHaveCount(0);
    await box.blur();
    await page.keyboard.press("j");
    await expect(page.locator(".fl-toggle").first()).toBeFocused();
  });
});
```

In `frontend/e2e/outline-causes.spec.ts`, in the test `"the review menu opens how to read the page; Escape closes it and returns to the menu"`, replace

```ts
    await expect(dialog).toContainText("J next, K back, F looks fine & next");
    await expect(dialog).toContainText("A faint violet line at the left of a paragraph marks text the AI wrote.");
```

with

```ts
    await expect(dialog).toContainText("J next, K back, F looks fine & next");
    await expect(dialog).toContainText("On Flows: J next row, K back, Enter opens it, F looks fine & next.");
    await expect(dialog).toContainText("A faint violet line at the left of a paragraph marks text the AI wrote.");
```

- [ ] **Step 2: Build and run them to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/flow-groups.spec.ts e2e/outline-causes.spec.ts -g "J and K move|Review Focus 4|how to read the page"`
Expected: FAIL — after J no `.fl-toggle` is focused; the dialog has no `On Flows:` line.

- [ ] **Step 3: Share the typing test**

Create `frontend/src/workspace/keys.ts`:

```ts
/** Keys a page acts on are letters while the reader types (spec 2026-10-16-outline-and-causes Review Focus 5,
 * 2026-10-25-review-ui-redesign Review Focus 4): in a text input, a text area, a select or editable text — not on a
 * tick box, a radio or a button, where they still step. */
export const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || t.tagName === "TEXTAREA" || t.tagName === "SELECT"
    || (t instanceof HTMLInputElement && !["checkbox", "radio", "button", "submit", "reset"].includes(t.type)));
```

In `frontend/src/workspace/CauseStepper.tsx`, replace

```tsx
const bare = (s: string) => s.replaceAll("`", "");
/** J, K and F are letters while the reader types (Review Focus 5). */
const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));
```

with

```tsx
const bare = (s: string) => s.replaceAll("`", "");
```

and replace `import { useWs } from "./context";` with

```tsx
import { useWs } from "./context";
import { typing } from "./keys";
```

- [ ] **Step 4: Give the tab its keys**

In `frontend/src/workspace/FlowsTab.tsx`:

replace `import { useEffect, useState } from "react";` with `import { useEffect, useRef, useState } from "react";`, and replace `import { useWs } from "./context";` with

```tsx
import { useWs } from "./context";
import { typing } from "./keys";
```

replace

```tsx
  useEffect(() => { if (lit) setOpen(lit); }, [lit]);
```

with

```tsx
  const [cur, setCur] = useState<number | null>(lit);                         // the row J, K and F act on
  useEffect(() => { if (lit) { setOpen(lit); setCur(lit); } }, [lit]);
```

replace

```tsx
  // a row an address or Next flow › opens unfolds its group
  const unfolded = (g: FlowGroup) => g.rows.length <= FOLD_AT || more.has(g.key) || g.rows.some((r) => r.n === lit || r.n === open);
```

with

```tsx
  // J, K and F (§7.3), read from a ref set in the render as the stepper's are: they wait while a mark is on its way and
  // stay the stepper's while a cause is open beside the page. Enter is the focused row's own button.
  const byN = new Map(flows.map((f, i) => [i + 1, f]));
  const leftAt = (n: number) => openKeys(places.get(byN.get(n)?.id ?? "") ?? [], marks);
  const focusRow = (n: number) => document.querySelector<HTMLElement>(`#flow-${n} .fl-toggle`)?.focus();
  const focusTo = useRef<number | null>(null);
  const move = (to: number | undefined) => {
    if (to === undefined) return;
    if (to === cur) focusRow(to);
    else { focusTo.current = to; setCur(to); }                               // focused once its group has unfolded
  };
  useEffect(() => {
    if (cur !== null && focusTo.current === cur) { focusTo.current = null; focusRow(cur); }
  }, [cur]);                                                                   // eslint-disable-line react-hooks/exhaustive-deps
  const onKey = useRef<(e: KeyboardEvent) => void>(() => {});
  onKey.current = (e) => {
    const stepper = !!ws.addr.open && "cause" in ws.addr.open;
    if (busy || stepper || e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || !order.length) return;
    const at = cur === null ? -1 : order.indexOf(cur);
    if (e.key === "j") { e.preventDefault(); move(order[at + 1]); }
    else if (e.key === "k") { e.preventDefault(); move(order[Math.max(at, 1) - 1]); }
    else if (e.key === "f" && cur !== null && at >= 0) {
      e.preventDefault();
      const left = leftAt(cur), next = [...order.slice(at + 1), ...order.slice(0, at)].find((n) => leftAt(n).length > 0);
      if (left.length) fine(left);
      move(next);
    }
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => onKey.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
  // a row an address, Next flow › or a key opens or reaches unfolds its group
  const unfolded = (g: FlowGroup) => g.rows.length <= FOLD_AT || more.has(g.key)
    || g.rows.some((r) => r.n === lit || r.n === open || r.n === cur);
```

and replace

```tsx
                            onClick={() => setOpen(on ? null : n)}>
```

with

```tsx
                            onClick={() => setOpen(on ? null : n)} onFocus={() => setCur(n)}>
```

- [ ] **Step 5: Say so in How to read this page**

In `frontend/src/workspace/HowToRead.tsx`, replace

```tsx
        <li><b>A story</b> has tabs: Flows (each path through the change, with its checks), Before → after, Where, Call
          paths, Code, Graph and Talk.</li>
```

with

```tsx
        <li><b>A story</b> has tabs: Flows (its flows grouped by what changed, a line each), Before → after, Where, Call
          paths, Code, Graph and Talk. On Flows: J next row, K back, Enter opens it, F looks fine &amp; next.</li>
```

- [ ] **Step 6: Build and run the specs to watch them pass**

Run: `cd frontend && npx tsc --noEmit && npm run build && E2E e2e/flow-groups.spec.ts e2e/outline-causes.spec.ts e2e/header-menu.spec.ts e2e/workspace-panels.spec.ts; rm -rf $(git rev-parse --show-toplevel)/.pwtmp`
Expected: PASS — including outline-causes' `"the stepper shows the change above each place; J, K and F step…"`, which now uses the shared `typing`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/workspace/keys.ts frontend/src/workspace/FlowsTab.tsx frontend/src/workspace/CauseStepper.tsx frontend/src/workspace/HowToRead.tsx frontend/e2e/flow-groups.spec.ts frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): J, K, Enter and F step through a story's flow rows, unless a check is open or the reader types

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 14: The outline lists the current story's flow groups, not its flows

**Files:**
- Modify: `frontend/src/workspace/Outline.tsx` (imports; `StoryFlows`), `frontend/src/workspace/workspace.css` (`.ws-row.flow` rules)
- Test: `frontend/e2e/flow-groups.spec.ts`, `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: `flowGroups`, `groupShort`, `openFlows`, `placesOf` (Task 11); the Flows tab's `flow=N` address (Task 12); `StoriesView` as Task 9 left it (it renders `<StoryFlows sid={st.id} onPick={onPick} />` under the current story).
- Produces: under the current story, `ol.ws-flows` > one `a.ws-row.fgroup` per flow group, `aria-label="Go to <field | writer's writes | function> · K flow(s)[, J open]"`, `title` without the open count, `aria-current="true"` while the addressed flow is in the group; it links to the story's Flows tab at the group's first flow (`?flow=N`).

- [ ] **Step 1: Write the failing tests**

In `frontend/e2e/flow-groups.spec.ts`, add inside `test.describe("a story with many flows", …)` after its last test:

```ts
  test("under the current story the outline lists a line per flow group, not per flow", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const rows = page.locator("aside.ws-outline .ws-flows .ws-row");
    await expect(rows).toHaveCount(6);                                               // not 140
    await expect(rows.first()).toHaveAttribute("aria-label", "Go to TelemDev::errors · 25 flows, 25 open");
    await expect(rows.first()).toHaveAttribute("title", "TelemDev::errors · 25 flows");
    await rows.nth(2).click();
    await expect(page).toHaveURL(/\/s\/S1\?flow=51$/);
    await expect(page.locator("#flow-51 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(rows.nth(2)).toHaveAttribute("aria-current", "true");
  });
```

In `frontend/e2e/outline-causes.spec.ts`, replace

```ts
  test("the outline's Stories: threads with open causes, the current story's flows", async ({ page }) => {
```

with

```ts
  test("the outline's Stories: threads with open causes, the current story's flow groups", async ({ page }) => {
```

replace

```ts
    const flows = outline.getByRole("link", { name: /^Go to flow / });
    await expect(flows.first()).toBeVisible();
    await flows.first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?flow=1$`));
```

with

```ts
    const groups = outline.locator(".ws-flows .ws-row");                             // a line per group of flows
    await expect(groups).toHaveCount(2);
    expect(await groups.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label"))))
      .toEqual(["Go to uart_send · 1 flow, 1 open", "Go to Uart::errors · 1 flow, 1 open"]);
    await groups.first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?flow=1$`));
```

replace

```ts
  test("an outline flow line opens its card; a story remembers its tab; an old ?view=graph opens Graph", async ({ page }) => {
```

with

```ts
  test("an outline group line opens its first row; a story remembers its tab; an old ?view=graph opens Graph", async ({ page }) => {
```

and replace

```ts
    await outline.getByRole("link", { name: /^Go to flow 1:/ }).click();
    await expect(page.locator("#flow-1 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeInViewport();
```

with

```ts
    await outline.getByRole("link", { name: /^Go to Uart::errors · 1 flow/ }).click();
    await expect(page).toHaveURL(/\/s\/S1\?flow=2$/);
    await expect(page.locator("#flow-2 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("region", { name: /^Flow 2:/ })).toBeInViewport();
```

- [ ] **Step 2: Build and run them to watch them fail**

Run: `cd frontend && npm run build && E2E e2e/flow-groups.spec.ts e2e/outline-causes.spec.ts -g "flow group|group line"`
Expected: FAIL — the outline has 140 (large) and 2 (demo) `.ws-flows .ws-row` links named `Go to flow N: …`.

- [ ] **Step 3: List the groups**

In `frontend/src/workspace/Outline.tsx`, replace

```tsx
import { flowLabel } from "../reading/story";
```

with

```tsx
import { flowGroups, groupShort, openFlows, placesOf } from "../reading/flowGroups";
```

and replace the whole `StoryFlows` function and its doc comment (`/** The current story's flows, numbered, one line each; a line opens the story's Flows tab at that flow's card. */`) with:

```tsx
/** The current story's flow groups (spec 2026-10-25-review-ui-redesign §7.6), one line each with how many flows and
 * how many still open; a line opens the story's Flows tab at the group's first flow. */
function StoryFlows({ sid, onPick }: { sid: string; onPick: () => void }) {
  const ws = useWs(), d = ws.data, storyOf = d.story;
  const [held, setHeld] = useState<{ sid: string; detail: StoryDetail } | null>(null);
  useEffect(() => {
    let live = true;
    storyOf(sid).then((x) => { if (live) setHeld({ sid, detail: x }); }).catch(() => { /* the page says why */ });
    return () => { live = false; };
  }, [sid, storyOf]);
  const det = held?.sid === sid ? held.detail : null;
  if (!det) return null;
  const flows = det.board.flows.filter((f) => det.story.flows.includes(f.id));
  if (!flows.length) return null;
  const labels = new Map(det.board.nodes.map((n) => [n.id, n.label]));
  const label = (n: string) => labels.get(n) ?? d.names[n]?.label ?? "a function";
  const places = placesOf(flows, det.reading?.checks ?? [], ws.hidden, label), marks = d.reading?.marks ?? {};
  const place: Place = { kind: "story", sid, view: "steps" };
  return (
    <ol className="ws-flows">{flowGroups(flows).map((g) => {
      const what = groupShort(g, label), k = g.rows.length, open = openFlows(g, places, marks);
      const count = `${k} flow${k === 1 ? "" : "s"}`, name = `${bare(what)} · ${count}`;
      return (
        <li key={g.key}>
          <Link className="ws-row fgroup" to={ws.link({ ...ws.item(place), place, sec: undefined, flow: g.rows[0].n })}
                aria-current={g.rows.some((r) => r.n === ws.addr.flow) ? "true" : undefined}
                aria-label={`Go to ${name}${open ? `, ${open} open` : ""}`} title={name} onClick={onPick}>
            <span className="ws-row-top"><span className="ws-one"><Ticks text={what} /><span className="ws-fg-n"> · {count}</span></span>
              {open > 0 && <span className="ck-count"><span className="vh">, </span>{open}<span className="vh"> open</span></span>}</span>
          </Link>
        </li>
      );
    })}</ol>
  );
}
```

In `frontend/src/workspace/workspace.css`, replace

```css
.ws-row.flow { padding-top: 3px; padding-bottom: 3px; font-size: 12.5px; }
.ws-row.flow .muted { flex: none; width: 1.4em; text-align: right; }
```

with

```css
.ws-row.fgroup { padding-top: 3px; padding-bottom: 3px; font-size: 12.5px; }
.ws-fg-n { color: var(--muted); }
```

- [ ] **Step 4: Build and run the specs to watch them pass**

Run: `cd frontend && npx tsc --noEmit && npm run build && E2E e2e/flow-groups.spec.ts e2e/outline-causes.spec.ts e2e/thread-sections.spec.ts e2e/long-text.spec.ts e2e/workspace-reading.spec.ts; rm -rf $(git rev-parse --show-toplevel)/.pwtmp`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/workspace/Outline.tsx frontend/src/workspace/workspace.css frontend/e2e/flow-groups.spec.ts frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): the outline lists the current story's flow groups, each linking to its first row

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

- [ ] **Step 6: Phase 3 gate — the whole suite**

Run: `cd backend && env PYTHONPATH=$PWD .venv/bin/python -m pytest -q -p no:cacheprovider tests && .venv/bin/ruff check codetortoise tests && cd ../frontend && npx vitest run && npm run build && E2E 2>&1 | tail -40; rm -rf $(git rev-parse --show-toplevel)/.pwtmp`
Expected: pytest, ruff, vitest and every e2e spec PASS. A failure in a spec this phase did not touch is investigated (superpowers:systematic-debugging), not skipped.

- [ ] **Step 7: Phase 3 screenshots for the owner**

Create the scratch spec `frontend/e2e/zz-shots.spec.ts` (never committed):

```ts
import { test } from "@playwright/test";
import { startReview } from "./helpers";

const OUT = "../.superpowers/screens/phase-3";

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test("phase 3", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page, "101 102 103 104");
    await page.goto(`${base}/s/S1?flow=2`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/flows-small.png` });
  });
});

test.describe("many flows", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });
  test("phase 3 many flows", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/flows-large.png` });
    await page.goto(`${base}/s/S1?flow=60`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/flows-large-open-row.png` });
  });
});

test.describe("phone", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 390, height: 844 } });
  test("phase 3 phone", async ({ page }) => {
    test.setTimeout(240_000);
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/flows-phone.png` });
  });
});
```

Run: `cd frontend && E2E e2e/zz-shots.spec.ts; rm e2e/zz-shots.spec.ts; rm -rf $(git rev-parse --show-toplevel)/.pwtmp; ls ../.superpowers/screens/phase-3 && git status --short`
Expected: four PNGs listed; `git status` shows no file this step made. Send the PNGs to the owner (SendUserFile, when the session has it) with one line: "Phase 3: a story's flows in groups by what changed, one line each, opening in place with a tick box; the outline lists the groups."
