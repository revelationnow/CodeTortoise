# One Server, Many Workspaces — Design

Date: 2026-10-31. Status: draft for review. Project 1 of 3: per-file viewer access follows in projects 2 and 3 (§3).

## 1. Why

Each `codetortoise serve` hosts exactly one workspace. `tortoise.yaml` has a single `workspace` section, and the
server holds one database, one symbol index, one compile database, one toolchain and one Perforce client. To review
changes from several workspaces, the owner runs several servers on several ports, and adding a workspace means writing
another `tortoise.yaml` and starting another server. The workspaces live on more than one Perforce server.

Goals (agreed 2026-10-31):
- **One server process hosts reviews for any number of workspaces**, on one or more Perforce servers.
- **Workspaces are added, edited and checked in the UI**, without editing `tortoise.yaml` or restarting.
- **Sign-in is per Perforce server.** A workspace's reviews are visible only to people signed in to its server; one
  sign-in covers every workspace on that server.
- **Review links stay `/r/<id>`**, so links already posted (Swarm comments, chat) keep their shape.
- **A broken workspace never stops the server** or any other workspace.
- **Nothing here blocks per-file viewer access** (projects 2 and 3).

## 2. Decisions (agreed 2026-10-31)

1. Workspaces may be on different Perforce servers, and several may share one.
2. Sign-in is per Perforce server: a person signs in to each server whose workspaces they want to see.
3. Start fresh: reviews held by today's separate servers are not carried over.
4. Workspaces are added at runtime in the UI and stored in the database. `tortoise.yaml` keeps the server-wide settings
   and may still name one *seed* workspace (§4).
5. One process and one database; each workspace gets its own bundle of the services a server has today (§6).
6. Viewers should see only what their Perforce protections let them read. That is split out of this project:
   project 2 learns each viewer's protections at sign-in, project 3 filters every view by them (§3).
7. Until project 3 lands, only owners add workspaces and create reviews; everyone else views. Opening creation to
   everyone signed in comes with project 3.

## 3. The three projects

1. **One server, many workspaces** (this spec). Workspaces in the database, a bundle per workspace, sign-in per
   Perforce server, visibility by server, owner rights per workspace.
2. **Protection snapshot.** At sign-in the server already holds the person's ticket from `p4 login -p`. It uses it once
   to read that person's own protection lines (`p4 protects`), keeps only those lines with that server's sign-in, and
   discards the ticket as today. A depot path is readable when those lines grant `read` on it. The file view, diffs and
   the changed-file list refuse files the viewer can't read. Before project 2 starts, the owner runs one probe on each
   Perforce server, signed in as an ordinary user: `p4 protects` must list that user's lines and not refuse.
3. **Show only what they can read.** Every analysis item (story, flow, finding, check, code snippet, board node, AI text,
   file summary) carries the depot files it was built from; each viewer gets the items whose files they can all read.
   Opening review creation and workspace adding to everyone signed in comes with it (decision 7).

Order: 1, 2, 3. This project leaves room for both: sign-ins are per server (where project 2 attaches the snapshot), and
review responses already carry the viewer's identity for that review (§8).

## 4. Configuration

`tortoise.yaml` keeps `server`, `llm`, `auth` and `analysis` (the defaults every workspace starts from). The
`owner`, `workspace`, `toolchain`, `targets` and `swarm` sections, when present, describe the **seed workspace**:

- It is registered at startup under `workspace.name` (a new optional key; default: the client's name, or the root
  folder's name for a git workspace) and refreshed from the file at every start.
- The UI shows it read-only ("set in tortoise.yaml").
- It keeps every file written for today's single-workspace server working: the lab, `fixture-demo`, the e2e servers,
  `codetortoise init`'s output.

The server needs at least one workspace to start: the seed, or one stored by an earlier run. With none it exits with a
message naming both ways in (a `workspace:` section, or a data folder that already holds one).

Each workspace's effective configuration merges the file with the workspace's own settings:
- `server`, `llm` and `auth` come from the file.
- `analysis` is the file's, overlaid with the workspace's analysis overrides.
- `workspace`, `toolchain`, `targets` and `swarm` are the workspace's own (the seed's come from the file).

## 5. Data

One database, `data/tortoise.db`:
- **`workspaces`**: `id`, `name` (unique), `vcs` (`p4` or `git`), `p4port`, `client`, `p4user` (the user Perforce
  reads run as), `root` (unique), `compile_commands`, `build_root`, `swarm_url`, `settings` (YAML text holding
  `toolchain`, `targets` and `analysis` overrides, with the same keys as `tortoise.yaml`), `source` (`config` or `ui`),
  `created_by`, `created_at`, `updated_at`.
- **`reviews.workspace_id`**: every review belongs to one workspace. Review ids stay global.
- **`session_logins`**: `token_hash`, `server`, `user`, `signed_in_at`. A browser session (the `ct_session` cookie, as
  today) holds at most one sign-in per Perforce server. `sessions` keeps the token and its expiry.
- **Key-value entries that belong to a workspace are keyed by its id**: the layer model, the flags libclang rejected,
  and the shared-sink marks (today one global entry).

Per workspace, on disk: `data/workspaces/<id>/symbols.db` and `data/workspaces/<id>/toolchain/`.

A workspace's **Perforce server** is its `p4port` as written, or `local` when it has none (git workspaces). Workspaces
with the same `p4port` share sign-ins. A git workspace may set `p4port` purely as a label, which is how dev mode and
the e2e tests get a second server without test-only code. Signing in to a git workspace's server works in dev mode
only: in `p4` mode there is no Perforce server to check the password against, so it is refused.

A workspace's name is 1–40 characters with no `/`, unique on the server; it is what the UI shows.

## 6. Runtime

**Per workspace, a bundle**: today's `Services`, built from the workspace's effective configuration — Perforce runner
and source (with `-p`, `-c` and `-u` passed explicitly, so workspaces with different users and servers don't share
environment), symbol index, compile database, toolchain, layer model, Swarm client, and a job queue that runs that
workspace's reviews and index builds one at a time. The pipeline keeps taking one bundle, unchanged. Reviews in
different workspaces run side by side, as they do today on separate servers.

**Shared by all workspaces**: the database, the weak and strong LLM clients, the AI ledger (budgets, request log), and
one AI worker pool with its job registry, so `llm.concurrency` stays a server-wide limit.

**The registry** loads every workspace at startup and builds its bundle in the background. A workspace whose bundle
fails to build (root missing, compile database unreadable) is kept with the reason and shown as not ready. An empty
symbol index is built when the bundle first loads. Adding a workspace builds its bundle; editing one builds a new
bundle and swaps it in. An edit while one of its reviews runs or waits is refused (409, "a review is running in this
workspace; try again when it finishes").

Amended after the reviews of the implementation (2026-11-01): an index build under way doesn't block an edit or a
remove. It is stopped, and the edited workspace's new bundle builds the index again once that build has ended. A
symbol index records the root, compile databases and scope it was built for, and while a build runs it records that
the build hasn't ended. A bundle whose index wasn't wholly built for its settings builds it again as it loads, so a
restart in the middle of any build loses nothing.

Startup chores that today run once per server (ending unfinished AI replies, failing AI calls left running, pruning
the request log) run once.

## 7. Sign-in and access

**Signing in.** The sign-in form asks for the Perforce server (a picker listing the servers of all workspaces; hidden
when there is only one), the user and the password. The server runs `p4 -p <server> -u <user> login -p` as today
(`-a` when the user is an owner there, for Swarm) and adds that sign-in to the browser's session, creating the session
if needed. Signing in to a second server adds a second sign-in to the same session. Sign out ends the whole session.
In dev mode any user name signs in to any server, as today.

**Who acts.** Inside a review the acting user is the session's sign-in on that review's server. Comments, ticks, marks
and AI calls record that user, as today; a review belongs to one server, so names are unambiguous inside it.

**Owners.** The owner of a workspace is its `p4user`, the Perforce user its reads run as (the seed's is today's
`owner`). A person has owner rights on a workspace when signed in to its server as that user.

| Action | Needs |
| --- | --- |
| See a review in the list; open it and everything under `/api/reviews/{id}/…` | a sign-in on the review's server |
| Edit or delete a comment | a sign-in on its review's server (author rules unchanged) |
| Create or re-run a review; finding states, AI budget and rounds, Swarm actions | owner of the review's workspace |
| A workspace's health, index rebuild, shared sinks; edit or remove it | owner of that workspace |
| Add a workspace | owner of at least one workspace |

A request for a review on a server the session isn't signed in to gets 401 with the server named
(`{"detail": "sign in required", "server": "<p4port>"}`), so the UI can offer that server's sign-in.

**Swarm.** Each workspace has its own Swarm URL. The owner's Swarm ticket is kept per Perforce server, taken when the
owner signs in there, as today.

**AI limits.** Per-review budgets are unchanged. The daily limit per person stays counted by user name, so two people
with the same name on two servers share one count (accepted).

## 8. API

Review paths (`/api/reviews/{id}/…`, `/api/comments/{id}`) keep their shape; they resolve the review's workspace and
apply §7. New or changed:

- `GET /api/servers` — the known Perforce servers (from the workspaces), each with the session's user there or null.
  Open to anyone who can reach the sign-in page.
- `POST /api/login` — `{server, user, password}`. `POST /api/logout` — ends the session.
- `GET /api/me` — `{logins: [{server, user}], owner_of: [workspace ids]}`.
- `GET /api/workspaces` — the workspaces on the session's servers: id, name, server, client, whether it is ready (and
  why not), whether the viewer owns it, whether it comes from `tortoise.yaml`. Owners also get its settings.
- `POST /api/workspaces` — add (owner of at least one workspace). Saved even when its checks fail; the response carries
  the checks.
- `POST /api/workspaces/detect` — `{root}`: values found at that root (P4CONFIG's server, client and user; compile
  databases), the same detection `codetortoise init` does, to fill the add form.
- `PUT /api/workspaces/{id}`, `DELETE /api/workspaces/{id}` — its owner. Refused for the seed (409, "set in
  tortoise.yaml") and, for delete, while it has reviews (409).
- `GET /api/workspaces/{id}/health`, `POST /api/workspaces/{id}/index/rebuild`, `GET/PUT/DELETE
  /api/workspaces/{id}/sinks…` — moved from `/api/health`, `/api/index/rebuild` and `/api/sinks`. Health keeps
  today's checks: the workspace ones (root, Perforce client, compile database, libclang, toolchain, Swarm) plus the
  server ones (front-end build, LLM endpoints).
- `GET /api/reviews` — the reviews on the session's servers, each with its workspace's id and name.
- `POST /api/reviews` — `{workspace_id, cls, title}`; owner of that workspace; refused while it isn't ready.
- `GET /api/reviews/{id}` — also carries `workspace: {id, name}` and `viewer: {user, is_owner}` (the acting user for
  this review). Inside a review, the UI takes "who am I" and "am I the owner" from `viewer`, not from `/api/me`.

## 9. Screens

- **Sign in**: server picker (hidden with one server), user, password. A review link for a server the session isn't
  signed in to shows "Sign in to `<server>` to open this review" with the same form in place, then opens the review.
- **⋯ menu**: one line per sign-in ("`<server>` as `<user>`") and "Sign in to another server".
- **Reviews**: each row shows its workspace; filter chips by workspace when there is more than one. Owners get New
  review with a workspace picker (the workspaces they own, the last used first), the CLs and a title.
- **Workspaces** (new; owners): the list (name, server, client, status, "set in tortoise.yaml" for the seed). Add
  workspace: name, server, client, user, root on this host (with "Fill from root"), compile database (auto or path),
  Swarm URL, and an Advanced box taking the `toolchain`, `targets` and `analysis` keys of `tortoise.yaml`. Per
  workspace: edit, remove, Rebuild index, and its Health (today's Health page, for that workspace).
- **Review page**: the workspace's name beside the review's title.

## 10. Command line

- `serve`, `init`, `fixture-demo`: unchanged (their files describe a seed workspace).
- `index`, `review`, `stories-check`, `check-parse`: a new `--workspace NAME` (default: the seed, else the only
  workspace; an error naming the choices when there are several and none is named).

## 11. Errors

- A workspace that can't load or fails a hard check (root, Perforce client, compile database, libclang): the server
  starts anyway; the workspace shows as not ready with the reason (Workspaces, its Health); its finished reviews stay
  readable; new reviews and re-runs there are refused with the reason until its checks pass.
- Adding a workspace runs the same checks and saves it even when they fail, so the owner can fix the host and press
  Recheck.
  Amended after the reviews of the implementation (2026-11-01): Recheck loads a workspace that isn't ready again, as
  an edit does, once none of its reviews waits or runs, so what was fixed since it loaded counts (a compile database
  made, a client synced). A Health page look that breaks leaves the load's own checks to decide whether it is ready.
- Refused: a second workspace with the same name or the same root (409); removing the seed or a workspace with reviews
  (409); editing while one of its reviews runs (409, §6).
- A Perforce server that is down: sign-in to it fails with Perforce's message; its workspaces show the client check's
  failure; other servers are unaffected.

## 12. Migration

Starting fresh (decision 3). On a database that already holds reviews (the lab), startup assigns them to the seed
workspace; old sign-ins end, so people sign in again; the seed's symbol index is rebuilt once into its new folder.

## 13. Testing

- **Back end**: the seed from `tortoise.yaml` (registered, refreshed, read-only); the workspaces store and the add, edit
  and remove rules; the effective configuration merge; bundles built per workspace and a failing one kept not ready;
  sign-in per server, one session holding two servers; the review list and every review path limited to the session's
  servers; the 401 naming the server; owner checks for every owner action, per workspace; the `--workspace` option.
  Pipeline tests stay as they are (one bundle).
- **Front end (vitest)**: the sign-in picker, workspace chips on Reviews, the add form and its validation, the
  identity read from `viewer` inside a review.
- **End to end**: a new two-workspace fixture server (two git fixture workspaces, one labelled with a second `p4port`)
  — sign in to one server, add a workspace in the UI, create a review in it, see both workspaces' reviews, open a link
  to a review on the other server and sign in from its prompt. The existing e2e servers keep their single-workspace
  files and run unchanged.
- **README**: setup becomes "one server; add workspaces on the Workspaces page", and the access section says that within
  one Perforce server everyone signed in still sees every review there until projects 2 and 3.

## 14. Out of scope

- Per-file viewer access (projects 2 and 3); review creation and workspace adding by non-owners (with project 3).
- Signing out of one server only.
- Moving a review to another workspace.
- Editing the seed workspace in the UI.
- Carrying over reviews from today's separate servers.
