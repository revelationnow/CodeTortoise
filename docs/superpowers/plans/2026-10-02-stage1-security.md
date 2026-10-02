# Stage 1 Security (Proof-of-Concept Safety Pack) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make plain-HTTP network exposure visible (optional HTTPS, startup warning, in-app banner), drop two unused endpoints, and record on every item a viewer can see the Perforce files it depends on, so stage 2 can filter by permission without redesigning the data.

**Architecture:** Server settings and a pure warning function in the backend; a browser-side banner rule in the frontend. File tags live on the existing pydantic models as `files: list[str] | None` (None = unknown). A new `provenance.py` derives structural tags from the board itself (`tag_board`, also applied when `/board` loads an old board), resolves every impact-graph node and evidence file once (`local_files`, `impact_node_files`, `finding_files`), and derives comment scopes (`comment_scope`). The storyboard records the files behind each LLM prompt as it applies the reply.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, uvicorn, pytest, ruff; React 19, TypeScript 5.9 (strict), Vite 8, vitest 5, Playwright (Chromium `--host-resolver-rules`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-01-review-board-design.md` §14 (stage 1 security). Earlier sections still apply where §14 is silent.

**Provenance:** every code block was run before the plan was written. The tasks were then replayed in order on a fresh tree from `main`: each task's tests failed before its implementation and passed after it, and the suites stayed green after every task. The replayed tree is byte-identical to the validated one. New files are given in full; changes to existing files are unified diffs against the previous task's state (`git apply`, or by hand).

## Global Constraints

- **Stage 1 filters nothing:** tags are recorded and returned by the API; no endpoint hides or changes what it serves because of them.
- **Tags:** `files: list[str] | None`, sorted and unique depot paths; `None` = unknown (stage 2: owner-only); `[]` = depends on no Perforce file (outside the workspace). A tag built from any unknown part is unknown.
- **Plain HTTP stays allowed** (warn, don't refuse). Loopback = `127.0.0.0/8`, `::1`, `localhost` (server); `localhost`, `127.x.x.x`, `[::1]` (browser).
- **Banner text:** `Not encrypted — this connection to CodeTortoise is plain HTTP over the network.` Startup warning: `Serving plain HTTP on <host>:<port> — logins (Perforce passwords) and source code cross the network unencrypted. Set server.tls_cert/tls_key, or bind 127.0.0.1.`
- **Stored data from older versions loads:** old boards (count in `AboutCl.files`, drift as strings, no tags) and old findings (no tags) must still load and display.
- **Dependencies:** none added.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).

## Review Focus

Conditions the spec implies that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **A phone on the LAN** (how the lab is used today): the banner plus the phone board must keep the tab bar on screen with no sideways scroll. Pinned by `e2e/banner.spec.ts` › "the banner and the phone board fit the screen together" (Task 2).
2. **Perforce lookups failing for context files:** tags must be unknown, never guessed, and the lookup made once. Pinned by `test_board_without_depot_paths_for_context_nodes_is_degraded` (Task 5).
3. **Boards stored before tags:** the change panel still shows changelist file counts and drift lines. Pinned by `test_boards_stored_before_tags_load_with_counts_and_drift_migrated` and `test_board_stored_before_file_tags_gets_them_on_load` (Task 4).
4. **Binding to `::` or a host name:** these are on the network and must be warned about. Pinned by `test_plain_http_on_the_network_is_warned_about` (Task 1).
5. **A certificate path with a typo:** a clear config error at startup, not a uvicorn traceback. Pinned by `test_a_missing_tls_file_is_a_config_error_not_a_startup_traceback` (Task 1).

---

### Task 1: Optional HTTPS and a startup warning for plain HTTP on the network

Spec §14.2. `server.tls_cert` and `server.tls_key` (resolved relative to the config file, like `data_dir`) make uvicorn
serve HTTPS and mark the session cookie `Secure`. Setting only one, or naming a file that does not exist, is a config
error. Plain HTTP stays allowed, but `codetortoise serve` warns on stderr and in the log when the host is not loopback
(`127.0.0.0/8`, `::1`, `localhost`); `0.0.0.0`, `::` and host names are all "on the network". The README explains both.

**Files:**
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/cli.py`
- Modify: `backend/codetortoise/web/app.py`
- Modify: `README.md`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_cli.py`
- Modify: `backend/tests/test_web.py`

**Interfaces:**
- Produces: `ServerConfig.tls_cert: Path | None`, `ServerConfig.tls_key: Path | None`; `cli.plain_http_warning(server:
  ServerConfig) -> str | None` (the warning text, or None when HTTPS is configured or the host is loopback).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_config.py`:

```diff
diff --git a/backend/tests/test_config.py b/backend/tests/test_config.py
index 0b92366..9200343 100644
--- a/backend/tests/test_config.py
+++ b/backend/tests/test_config.py
@@ -40,3 +40,29 @@ def test_git_workspace_needs_no_p4(tmp_path):
 def test_invalid_yaml_is_config_error(tmp_path):
     with pytest.raises(ConfigError):
         load_config(write(tmp_path, "owner: [unclosed\n"))
+
+
+def test_tls_cert_and_key_resolve_relative_to_the_config(tmp_path):
+    (tmp_path / "certs").mkdir()
+    (tmp_path / "certs/ct.pem").write_text("cert")
+    (tmp_path / "certs/ct.key").write_text("key")
+    cfg = load_config(write(tmp_path, """
+owner: a
+workspace: {vcs: git, root: /w, compile_commands: /w/cc.json}
+server: {host: 0.0.0.0, tls_cert: certs/ct.pem, tls_key: certs/ct.key}
+"""))
+    assert cfg.server.tls_cert == (tmp_path / "certs/ct.pem").resolve()
+    assert cfg.server.tls_key == (tmp_path / "certs/ct.key").resolve()
+
+
+def test_tls_cert_without_key_is_a_config_error(tmp_path):
+    with pytest.raises(ConfigError, match="tls_cert and server.tls_key"):
+        load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"
+                                      "server: {tls_cert: ct.pem}\n"))
+
+
+def test_a_missing_tls_file_is_a_config_error_not_a_startup_traceback(tmp_path):
+    (tmp_path / "ct.pem").write_text("cert")
+    with pytest.raises(ConfigError, match="server.tls_key: no such file"):
+        load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"
+                                      "server: {tls_cert: ct.pem, tls_key: ct.key}\n"))
```

`backend/tests/test_cli.py`:

```diff
diff --git a/backend/tests/test_cli.py b/backend/tests/test_cli.py
index cb26958..c034c2a 100644
--- a/backend/tests/test_cli.py
+++ b/backend/tests/test_cli.py
@@ -18,3 +18,19 @@ def test_bad_config_exit_code(tmp_path, capsys):
     (tmp_path / "bad.yaml").write_text("owner: x\n")
     assert main(["index", "--config", str(tmp_path / "bad.yaml")]) == 2
     assert "config error" in capsys.readouterr().err
+
+
+def test_plain_http_on_the_network_is_warned_about():
+    from pathlib import Path
+
+    from codetortoise.cli import plain_http_warning
+    from codetortoise.config import ServerConfig
+    w = plain_http_warning(ServerConfig(host="0.0.0.0", port=8767))
+    assert w is not None and w.startswith("Serving plain HTTP on 0.0.0.0:8767")
+    assert "Set server.tls_cert/tls_key, or bind 127.0.0.1." in w
+    for host in ("192.168.1.122", "::", "myhost.local"):                  # IPv6 any-address and host names too
+        assert plain_http_warning(ServerConfig(host=host)) is not None
+    for host in ("127.0.0.1", "127.0.1.1", "::1", "localhost"):
+        assert plain_http_warning(ServerConfig(host=host)) is None
+    tls = ServerConfig(host="0.0.0.0", tls_cert=Path("/c.pem"), tls_key=Path("/c.key"))
+    assert plain_http_warning(tls) is None
```

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 4baaa2f..cffb10d 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -249,3 +249,15 @@ def test_board_stored_by_an_older_version_gets_current_defaults(env):
     assert all(i["landing"] is False and i["cause"] is None for i in b["impacts"])
     assert len(b["flows"]) == 3
     assert [f["title"] for f in b["flows"]] == ["affects uart_errors", "-2 ignored", "signature changed"]
+
+
+def test_session_cookie_is_secure_only_when_https_is_configured(fx, tmp_path):
+    from pathlib import Path
+    svc = make_services(fx, tmp_path)
+    plain = TestClient(create_app(svc, InlineRunner(svc), make_authenticator(svc)))
+    r = plain.post("/api/login", json={"user": "anoop", "password": "x"})
+    assert "secure" not in r.headers["set-cookie"].lower()
+    svc.cfg.server.tls_cert, svc.cfg.server.tls_key = Path("/c.pem"), Path("/c.key")
+    tls = TestClient(create_app(svc, InlineRunner(svc), make_authenticator(svc)))
+    r = tls.post("/api/login", json={"user": "anoop", "password": "x"})
+    assert "secure" in r.headers["set-cookie"].lower()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_cli.py tests/test_web.py -q`
Expected: FAIL — `5 failed, 24 passed` (`AttributeError: 'ServerConfig' object has no attribute 'tls_cert'`, `ImportError: cannot import name 'plain_http_warning'`, `DID NOT RAISE ConfigError`)

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index 75b8e6b..1c55759 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -13,6 +13,8 @@ class ServerConfig(BaseModel):
     port: int = 8765
     public_url: str = "http://127.0.0.1:8765"
     data_dir: Path = Path(".tortoise")
+    tls_cert: Path | None = None     # both set: serve HTTPS (spec §14.2)
+    tls_key: Path | None = None
 
 
 class WorkspaceConfig(BaseModel):
@@ -99,4 +101,13 @@ def load_config(path: Path) -> Config:
     ws.compile_commands = (base / ws.compile_commands).resolve() if not ws.compile_commands.is_absolute() else ws.compile_commands
     if not cfg.server.data_dir.is_absolute():
         cfg.server.data_dir = (base / cfg.server.data_dir).resolve()
+    srv = cfg.server
+    if (srv.tls_cert is None) != (srv.tls_key is None):
+        raise ConfigError("server.tls_cert and server.tls_key must be set together")
+    if srv.tls_cert is not None and srv.tls_key is not None:
+        srv.tls_cert = srv.tls_cert if srv.tls_cert.is_absolute() else (base / srv.tls_cert).resolve()
+        srv.tls_key = srv.tls_key if srv.tls_key.is_absolute() else (base / srv.tls_key).resolve()
+        for name, f in (("tls_cert", srv.tls_cert), ("tls_key", srv.tls_key)):
+            if not f.is_file():
+                raise ConfigError(f"server.{name}: no such file: {f}")
     return cfg
```

`backend/codetortoise/cli.py`:

```diff
diff --git a/backend/codetortoise/cli.py b/backend/codetortoise/cli.py
index a17b079..318c8ef 100644
--- a/backend/codetortoise/cli.py
+++ b/backend/codetortoise/cli.py
@@ -2,13 +2,31 @@
 from __future__ import annotations
 
 import argparse
+import ipaddress
 import logging
 import sys
 from pathlib import Path
 
 import yaml
 
-from codetortoise.config import ConfigError, load_config
+from codetortoise.config import ConfigError, ServerConfig, load_config
+
+
+def _loopback(host: str) -> bool:
+    if host == "localhost":
+        return True
+    try:
+        return ipaddress.ip_address(host).is_loopback
+    except ValueError:
+        return False
+
+
+def plain_http_warning(server: ServerConfig) -> str | None:
+    """The startup warning for plain HTTP reachable beyond this machine (spec §14.2), or None."""
+    if server.tls_cert is not None or _loopback(server.host):
+        return None
+    return (f"Serving plain HTTP on {server.host}:{server.port} — logins (Perforce passwords) and source code cross the "
+            "network unencrypted. Set server.tls_cert/tls_key, or bind 127.0.0.1.")
 
 
 def _services(config: str):
@@ -29,7 +47,14 @@ def cmd_serve(args) -> int:
     app = create_app(svc, runner, make_authenticator(svc))
     if svc.cfg.auth.mode == "dev":
         logging.warning("auth.mode=dev: any username logs in without a password. Do not expose this server.")
-    uvicorn.run(app, host=svc.cfg.server.host, port=svc.cfg.server.port)
+    srv = svc.cfg.server
+    warning = plain_http_warning(srv)
+    if warning:
+        print(f"WARNING: {warning}", file=sys.stderr)
+        logging.warning(warning)
+    uvicorn.run(app, host=srv.host, port=srv.port,
+                ssl_certfile=str(srv.tls_cert) if srv.tls_cert else None,
+                ssl_keyfile=str(srv.tls_key) if srv.tls_key else None)
     return 0
 
 
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index cc3ed9d..49c291b 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -96,7 +96,8 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         if body.user == cfg.owner:
             svc.owner_ticket = ticket
         token = store.create_session(body.user)
-        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 86400)
+        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 86400,
+                            secure=cfg.server.tls_cert is not None)
         return {"user": body.user, "is_owner": body.user == cfg.owner}
 
     @app.post("/api/logout")
```

`README.md`:

````diff
diff --git a/README.md b/README.md
index 3430ccf..a4c5187 100644
--- a/README.md
+++ b/README.md
@@ -74,6 +74,8 @@ server:
   port: 8765
   public_url: "https://codetortoise.example.com"   # what shared links and Swarm summaries point to
   data_dir: /var/lib/codetortoise   # SQLite database, symbol index, toolchain cache
+  # tls_cert: /etc/codetortoise/ct.pem   # both set: serve HTTPS directly (plain HTTP on a network address
+  # tls_key: /etc/codetortoise/ct.key    #   is allowed but warned about at startup and in a banner)
 workspace:
   vcs: p4
   p4port: ssl:perforce.example.com:1666
@@ -224,8 +226,10 @@ Restart=on-failure
 WantedBy=multi-user.target
 ```
 
-The app speaks plain HTTP. Beyond a trusted LAN or VPN, put it behind a TLS-terminating reverse proxy (nginx, Caddy,
-your ingress) and set `server.public_url` to the HTTPS address. Proxy `/api/reviews/*/events` without buffering
+The app speaks plain HTTP unless `server.tls_cert` and `server.tls_key` are set. On a network address over plain HTTP
+it prints a warning at startup and every page shows a "Not encrypted" banner. Beyond a trusted LAN or VPN, set the
+certificate or put it behind a TLS-terminating reverse proxy (nginx, Caddy, your ingress), and set `server.public_url`
+to the HTTPS address. Proxy `/api/reviews/*/events` without buffering
 (server-sent events), for example `proxy_buffering off;` in nginx. Sessions are HTTP-only cookies. There is no built-in
 sign-in rate limit; Perforce's own login policies apply.
 
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_cli.py tests/test_web.py -q`
Expected: `29 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `203 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/cli.py backend/codetortoise/web/app.py README.md backend/tests/test_config.py backend/tests/test_cli.py backend/tests/test_web.py
git commit -m "feat(server): optional HTTPS and a startup warning for plain HTTP on the network"
```

---

### Task 2: Plain-HTTP banner on every page

Spec §14.2: an amber strip, "Not encrypted — this connection to CodeTortoise is plain HTTP over the network.", above the
top bar on every page, login included. The browser decides from its own location: `http:` and a host that is not
`localhost`, `127.x.x.x` or `[::1]`. Behind a TLS-terminating proxy the page is `https:`, so the banner correctly stays
away. The e2e test reaches the same loopback server through a second host name, `ct-lan.test`, mapped by Chromium's
`--host-resolver-rules`; on a phone the banner and the phone board must still fit the screen.

**Files:**
- Create: `frontend/src/lib/insecure.ts`
- Create: `frontend/src/components/InsecureBanner.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/lib/insecure.test.ts`
- Test: `frontend/e2e/banner.spec.ts`

**Interfaces:**
- Produces: `lib/insecure.ts`: `plainHttpOnNetwork(protocol: string, hostname: string): boolean`;
  `components/InsecureBanner.tsx` (default export, `role="alert"`, class `insecure`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/lib/insecure.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { plainHttpOnNetwork } from "./insecure";

describe("plain-HTTP banner rule (spec §14.2)", () => {
  it("shows for http on a network host", () => {
    expect(plainHttpOnNetwork("http:", "192.168.1.122")).toBe(true);
    expect(plainHttpOnNetwork("http:", "codetortoise.example.com")).toBe(true);
    expect(plainHttpOnNetwork("http:", "[fe80::1]")).toBe(true);
  });

  it("hides for https and for loopback hosts", () => {
    expect(plainHttpOnNetwork("https:", "192.168.1.122")).toBe(false);
    for (const h of ["localhost", "127.0.0.1", "127.1.2.3", "[::1]"]) expect(plainHttpOnNetwork("http:", h)).toBe(false);
  });
});
```

`frontend/e2e/banner.spec.ts`:

```ts
import { devices, expect, test } from "@playwright/test";
import { login, startReview } from "./helpers";

// a second name for the e2e server that is not loopback (spec §14.5); 127.0.0.1 itself is unaffected
test.use({ launchOptions: { args: ["--host-resolver-rules=MAP ct-lan.test 127.0.0.1"] } });

const banner = "Not encrypted — this connection to CodeTortoise is plain HTTP over the network.";

test("no plain-HTTP banner on a loopback address", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText(banner)).toHaveCount(0);
});

test.describe("on a network host name", () => {
  test.use({ baseURL: "http://ct-lan.test:8799" });

  test("the plain-HTTP banner shows on the login page and on a review", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("alert")).toHaveText(banner);
    await login(page);
    await startReview(page);
    await expect(page.getByRole("alert")).toHaveText(banner);
  });

  test.describe("on a phone", () => {
    test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent, isMobile: true, hasTouch: true });

    test("the banner and the phone board fit the screen together", async ({ page }) => {
      await startReview(page);
      await expect(page.getByRole("alert")).toBeVisible();
      const tabs = (await page.locator(".ph-tabs").boundingBox())!;
      expect(tabs.y + tabs.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);   // the tab bar stays on screen
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    });
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/lib/insecure.test.ts && npm run build && npx playwright test e2e/banner.spec.ts`
Expected: FAIL — `Error: Cannot find module './insecure'` (the build and e2e steps do not run yet)

- [ ] **Step 3: Implement**

`frontend/src/lib/insecure.ts`:

```ts
/** Spec §14.2: the page reached CodeTortoise over plain HTTP from another machine (a TLS proxy in front makes it https:). */
export function plainHttpOnNetwork(protocol: string, hostname: string): boolean {
  if (protocol !== "http:") return false;
  const h = hostname.toLowerCase();
  return !(h === "localhost" || h === "[::1]" || /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(h));
}
```

`frontend/src/components/InsecureBanner.tsx`:

```tsx
import { plainHttpOnNetwork } from "../lib/insecure";

/** Amber strip on every page while the connection is plain HTTP over the network (spec §14.2). */
export default function InsecureBanner() {
  if (!plainHttpOnNetwork(window.location.protocol, window.location.hostname)) return null;
  return <div className="insecure" role="alert">Not encrypted — this connection to CodeTortoise is plain HTTP over the network.</div>;
}
```

`frontend/src/App.tsx`:

```diff
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index e5ae7e7..d02b7ea 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -1,6 +1,7 @@
 import { createContext, useContext, useEffect, useState } from "react";
 import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
 import { api, type Me } from "./api";
+import InsecureBanner from "./components/InsecureBanner";
 import Logo from "./components/Logo";
 import ThemeSwitch from "./components/ThemeSwitch";
 import Health from "./pages/Health";
@@ -28,6 +29,7 @@ export default function App() {
 
   return (
     <MeContext.Provider value={me}>
+      <InsecureBanner />
       <header className={`topbar${menu ? " open" : ""}`}>
         <Link to="/" className="brand"><Logo size={28} />CodeTortoise</Link>
         {me && (
```

`frontend/src/styles.css`:

```diff
diff --git a/frontend/src/styles.css b/frontend/src/styles.css
index 571a0d6..828b7e4 100644
--- a/frontend/src/styles.css
+++ b/frontend/src/styles.css
@@ -17,6 +17,8 @@ body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(-
 #root { display: flex; flex-direction: column; height: 100vh; height: 100dvh; }
 #root > main { flex: 1; min-height: 0; overflow: auto; width: 100%; }
 #root > .topbar { flex: none; }
+#root > .insecure { flex: none; padding: 5px 16px; background: #f5b83d; color: #2b1a00; font: 600 12.5px/1.4 var(--sans);
+  text-align: center; }
 .review { display: flex; flex-direction: column; overflow: hidden !important; }
 .review-body { flex: 1; min-height: 0; overflow: auto; padding: 16px 24px; }
 .review.board { overflow: hidden; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/insecure.test.ts && npm run build && npx playwright test e2e/banner.spec.ts`
Expected: `Tests  2 passed (2)` and `✓ built in …` and `3 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  69 passed (69)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/insecure.ts frontend/src/components/InsecureBanner.tsx frontend/src/App.tsx frontend/src/styles.css frontend/src/lib/insecure.test.ts frontend/e2e/banner.spec.ts
git commit -m "feat(ui): banner on every page while the connection is plain HTTP over the network"
```

---

### Task 3: Drop the unused storyboard and impact endpoints

Spec §14.4. `GET /api/reviews/{id}/storyboard` and `GET /api/reviews/{id}/impact` serve the raw layer narratives and
impact graph; nothing in the frontend calls them since the board replaced those tabs. Remove both routes and their
`api.ts` entries and types, so there are two fewer surfaces to tag and secure. The stored blobs stay (the board is built
from them). The layer-rename test now reads layer names from the board.

**Files:**
- Modify: `backend/codetortoise/web/app.py`
- Modify: `frontend/src/api.ts`
- Modify: `backend/tests/test_web.py`

**Interfaces:**
- Produces: nothing new; `/api/reviews/{id}/storyboard` and `/impact` return 404 (the SPA fallback rejects `api/`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index cffb10d..b81679c 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -64,8 +64,10 @@ def test_owner_creates_review_others_view_and_comment(env):
     rid = r.json()["id"]
     detail = bob.get(f"/api/reviews/{rid}").json()
     assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 11
-    assert bob.get(f"/api/reviews/{rid}/storyboard").json()["storyboard"]["risk"] == "high"
-    assert len(bob.get(f"/api/reviews/{rid}/impact").json()["nodes"]) > 5
+    assert detail["review"]["risk"] == "high"
+    # the raw storyboard and impact graph are not served: the board replaced them (spec §14.4)
+    assert bob.get(f"/api/reviews/{rid}/storyboard").status_code == 404
+    assert bob.get(f"/api/reviews/{rid}/impact").status_code == 404
     assert len(bob.get(f"/api/reviews/{rid}/findings").json()) == 6
     assert [f["depot"] for f in bob.get(f"/api/reviews/{rid}/files").json()][0] == "//fixture/driver/uart.c"
     ev = bob.get(f"/api/reviews/{rid}/events")
@@ -117,7 +119,7 @@ def test_health_and_layer_rename(env):
     assert h["ready"] is True and {c["name"] for c in h["checks"]} >= {"workspace root", "compile_commands", "libclang"}
     assert owner.put("/api/layers/2", json={"name": "Drivers"}).json() == {"2": "Drivers"}
     rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
-    names = [c["name"] for c in owner.get(f"/api/reviews/{rid}/storyboard").json()["storyboard"]["chapters"]]
+    names = [layer["name"] for layer in owner.get(f"/api/reviews/{rid}/board").json()["layers"]]
     assert "Drivers" in names and "L2: driver" not in names
     assert login(app, "bob").put("/api/layers/2", json={"name": "x"}).status_code == 403
 
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_web.py -q`
Expected: FAIL — `1 failed, 18 passed` — `assert 200 == 404` (the storyboard endpoint still answers)

- [ ] **Step 3: Implement**

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 49c291b..e08f688 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -165,17 +165,6 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
 
         return StreamingResponse(gen(), media_type="text/event-stream")
 
-    @app.get("/api/reviews/{rid}/storyboard")
-    def storyboard(rid: int, _: str = Depends(user_of)):
-        review_or_404(rid)
-        cs = store.get_blob(rid, "changeset") or {}
-        sb, layers = store.get_blob(rid, "storyboard"), store.get_blob(rid, "layers")
-        overrides = store.kv_get("layer_overrides") or {}
-        for item in (sb or {}).get("chapters", []) + (layers or {}).get("layers", []):
-            if str(item.get("level")) in overrides:
-                item["name"] = overrides[str(item["level"])]
-        return {"storyboard": sb, "drift": cs.get("drift", []), "layers": layers}
-
     @app.get("/api/reviews/{rid}/board")
     def board(rid: int, _: str = Depends(user_of)):
         review_or_404(rid)
@@ -215,11 +204,6 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
             store.put_blob(rid, key, cached)
         return cached
 
-    @app.get("/api/reviews/{rid}/impact")
-    def impact(rid: int, _: str = Depends(user_of)):
-        review_or_404(rid)
-        return store.get_blob(rid, "impact")
-
     @app.get("/api/reviews/{rid}/findings")
     def findings(rid: int, _: str = Depends(user_of)):
         review_or_404(rid)
```

`frontend/src/api.ts`:

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index 7281ae3..296fd11 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -11,35 +11,12 @@ export interface SwarmInfo { id: number; state: string; state_label?: string; ur
 export interface ClRow { review_id: number; cl: number; status: string; user: string | null; description: string | null; swarm: SwarmInfo | null }
 export interface ReviewDetail { review: ReviewRow; cls: ClRow[]; stages: Stage[] }
 
-export interface Node {
-  id: string; key: string; kind: "function" | "field"; label: string; file: string | null; line: number | null;
-  status: "added" | "removed" | "changed" | "unchanged"; layer: number | null; confidence: "precise" | "heuristic";
-}
-export interface Edge {
-  id: string; src: string; dst: string; kind: "call" | "virtual" | "writes" | "reads";
-  status: "added" | "removed" | "unchanged"; confidence: "precise" | "may" | "heuristic"; file: string | null; line: number | null;
-}
-export interface Flow { root: string; nodes: string[]; edges: string[] }
-export interface BlastItem { node: string; hop: number; score: number; via: "call" | "data"; path: string[] }
-export interface FanOut { header: string; total_tus: number; by_layer: Record<string, number> }
-export interface Impact { nodes: Record<string, Node>; edges: Edge[]; changed: string[]; flows: Flow[]; blast: BlastItem[]; fanout: FanOut[] }
-
 export interface Evidence { text: string; file: string | null; line: number | null; severity: Severity }
 export interface Cited { text: string; cites: string[]; verified: boolean }
 export interface Finding {
   id: string; kind: string; severity: Severity; title: string; nodes: string[]; evidence: Evidence[]; summary: string;
   explanation: string | null; verify_steps: string[]; hypotheses: Cited[]; state: "open" | "ack" | "dismissed";
 }
-export interface Chapter {
-  level: number | null; name: string; narrative: string; cites: string[]; verified: boolean;
-  cross_layer_effects: Cited[]; nodes: string[]; findings: string[];
-}
-export interface Storyboard {
-  summary: string; risk: "low" | "medium" | "high"; review_order: string[]; verified: boolean;
-  chapters: Chapter[]; llm_used: boolean; llm_error: string | null;
-}
-export interface Drift { depot: string; local: string; expected: string; actual: string }
-export interface StoryboardResponse { storyboard: Storyboard | null; drift: Drift[] }
 export interface PerCl { cl: number; before: string; after: string }
 export interface FileChange { depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[] }
 export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review";
@@ -82,8 +59,6 @@ export const api = {
   createReview: (cls: number[], title?: string) => call<ReviewRow>("POST", "/api/reviews", { cls, title }),
   review: (id: number) => call<ReviewDetail>("GET", `/api/reviews/${id}`),
   rerun: (id: number) => call("POST", `/api/reviews/${id}/rerun`),
-  storyboard: (id: number) => call<StoryboardResponse>("GET", `/api/reviews/${id}/storyboard`),
-  impact: (id: number) => call<Impact | null>("GET", `/api/reviews/${id}/impact`),
   board: (id: number) => call<Board>("GET", `/api/reviews/${id}/board`),
   source: (id: number, path: string, side: "before" | "after" = "after") =>
     call<SourceText>("GET", `/api/reviews/${id}/source?${new URLSearchParams({ path, side })}`),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_web.py -q`
Expected: `19 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q && cd ../frontend && npx vitest run && npx tsc --noEmit`
Expected: `All checks passed!`, `203 passed`, `Tests  69 passed (69)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/web/app.py frontend/src/api.ts backend/tests/test_web.py
git commit -m "refactor(api): drop the unused storyboard and impact endpoints"
```

---

### Task 4: File tags on the board and the change summary

Spec §14.3. Every visible board item records the depot paths it depends on (`files`, `None` = unknown, fail closed).
`provenance.tag_board` derives all structural tags from the board itself, so a board stored before tags gets the same
tags when `/board` loads it: a node's own path, or for a node without one the paths of the board nodes calling or
reading it; edges, impacts, flows and layers from their nodes; tree files themselves; each changelist its tree files;
template intent all changed files. The changelist count moves from `files` to `file_count` and drift lines become
`{text, files}`; validators migrate stored boards. LLM-rewritten flow text and intent clear their tags (Task 6 records
the real ones). The pipeline tags the board it stores; the frontend reads `file_count` and `drift[].text`.

**Files:**
- Modify: `backend/codetortoise/board.py`
- Create: `backend/codetortoise/provenance.py`
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/web/app.py`
- Modify: `frontend/src/board/types.ts`
- Modify: `frontend/src/board/ChangePanel.tsx`
- Modify: `frontend/src/pages/Review.tsx`
- Test: `backend/tests/test_provenance.py`
- Modify: `backend/tests/test_board.py`
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/tests/test_storyboard.py`
- Modify: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: `Board` and its item models (`board.py`).
- Produces: `board.Files = list[str] | None`; `files: Files` on `BoardNode`, `BoardEdge`, `Impact`, `Flow`,
  `BoardLayer`, `AboutFile`, `AboutCl`, `AboutWhy`, `AboutDrift`; `Flow.what_files`, `About.intent_files`;
  `AboutCl.file_count: int`; `AboutDrift {text, files}`; `provenance.merge(*parts) -> Files`;
  `provenance.tag_board(board, finding_files: dict[str, Files] | None = None) -> Board`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_provenance.py`:

```python
"""File tags on every visible item (spec §14.3)."""
from codetortoise.board import About, AboutDir, AboutFile, Board, BoardEdge, BoardNode, Flow
from codetortoise.provenance import tag_board
from tests.test_board import board  # noqa: F401  (module fixture: the fixture review's board)

D = "//fixture/"


def test_every_item_on_the_fixture_board_is_tagged(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True))
    items = [*b.nodes, *b.edges, *b.impacts, *b.flows, *b.layers, *b.about.cls,
             *(f for d in b.about.tree for f in d.files)]
    assert items and all(i.files for i in items)
    assert all(f.what_files == f.files for f in b.flows)                  # template text: the flow's own files
    assert b.about.intent_files == sorted(f.path for d in b.about.tree for f in d.files)


def test_fixture_tags_are_exact(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True))
    fl1 = next(f for f in b.flows if f.id == "FL1")
    assert fl1.files == [D + "app/main.c", D + "driver/uart.c", D + "driver/uart.h", D + "service/logger.c"]
    by_cl = {c.cl: c.files for c in b.about.cls}
    assert by_cl == {101: [D + "driver/uart.c"], 102: [D + "driver/uart.h", D + "hal/regs.c", D + "include/hal/regs.h"]}
    assert [c.file_count for c in b.about.cls] == [1, 3]
    assert next(layer.files for layer in b.layers if layer.name == "driver") == [D + "driver/uart.c", D + "driver/uart.h"]
    imp = next(i for i in b.impacts if i.node == "N8" and i.line == 8)   # uart_init calls hal_write (changed)
    assert imp.files == [D + "driver/uart.c", D + "hal/regs.c"]


def test_why_lines_take_their_findings_files_and_are_unknown_without_them(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True), {"F1": [D + "driver/uart.c", D + "driver/uart.h"]})
    assert b.about.why[0].finding == "F1" and b.about.why[0].files == [D + "driver/uart.c", D + "driver/uart.h"]
    assert all(w.files is None for w in b.about.why[1:])


def _tiny(**about):
    nodes = [BoardNode(id="A", key="a", label="caller", path="//d/a.c"),
             BoardNode(id="B", key="b", label="hal_read"),                 # no visible definition
             BoardNode(id="C", key="c", label="orphan")]                   # no definition, nothing calls it
    edges = [BoardEdge(src="A", dst="B", kind="call", status="unchanged", confidence="precise"),
             BoardEdge(src="B", dst="C", kind="call", status="unchanged", confidence="precise")]
    flow = Flow(id="FL1", path=["A", "B"], tag="contract", lands="A", severity="medium", text="caller → hal_read",
                what="w", effect="e", check="c")
    return Board(nodes=nodes, edges=edges, flows=[flow],
                 about=About(intent="i", tree=[AboutDir(dir=".", files=[AboutFile(path="//d/a.c", name="a.c", action="edit",
                                                                                  cls=[1], add=1, rem=0)])], **about))


def test_a_node_without_a_path_takes_its_callers_files_else_is_unknown():
    b = tag_board(_tiny())
    files = {n.id: n.files for n in b.nodes}
    assert files == {"A": ["//d/a.c"], "B": ["//d/a.c"], "C": None}
    assert [e.files for e in b.edges] == [["//d/a.c"], None]               # unknown on either end: unknown
    assert b.flows[0].files == ["//d/a.c"]


def test_llm_text_keeps_its_recorded_files_and_is_unknown_when_none_were_recorded():
    b = _tiny(intent_source="llm")
    b.flows[0].what_source = "llm"
    tagged = tag_board(b.model_copy(deep=True))
    assert tagged.flows[0].what_files is None and tagged.about.intent_files is None
    b.flows[0].what_files, b.about.intent_files = ["//d/a.c", "//d/z.c"], ["//d/a.c"]
    tagged = tag_board(b)
    assert tagged.flows[0].what_files == ["//d/a.c", "//d/z.c"] and tagged.about.intent_files == ["//d/a.c"]


def test_boards_stored_before_tags_load_with_counts_and_drift_migrated():
    old = _tiny().model_dump()
    old["about"]["cls"] = [{"cl": 1, "user": "u", "description": "d", "files": 1}]
    old["about"]["drift"] = ["//d/a.c (base #3, workspace #4)"]
    b = tag_board(Board.model_validate(old))
    assert b.about.cls[0].file_count == 1 and b.about.cls[0].files == ["//d/a.c"]
    assert b.about.drift[0].text == "//d/a.c (base #3, workspace #4)" and b.about.drift[0].files == ["//d/a.c"]
```

`backend/tests/test_board.py`:

```diff
diff --git a/backend/tests/test_board.py b/backend/tests/test_board.py
index 98991af..c23f547 100644
--- a/backend/tests/test_board.py
+++ b/backend/tests/test_board.py
@@ -240,7 +240,8 @@ def test_about_lists_workspace_drift():
     from codetortoise.vcs.model import DriftItem
     ctx, _ = _synthetic()
     ctx.cs.drift = [DriftItem(depot="//d/lib/src/a.c", local="/w/a.c", expected="#3", actual="#4")]
-    assert build_board(ctx).about.drift == ["//d/lib/src/a.c (base #3, workspace #4)"]
+    drift = build_board(ctx).about.drift
+    assert [(d.text, d.files) for d in drift] == [("//d/lib/src/a.c (base #3, workspace #4)", ["//d/lib/src/a.c"])]
     assert build_board(_synthetic()[0]).about.drift == []
 
 
```

`backend/tests/test_pipeline.py`:

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 0254946..3cb1d59 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -29,6 +29,7 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
     assert [f["tag"] for f in board["flows"]] == ["state", "contract", "contract"]
     assert all(n["path"].startswith("//fixture/") for n in board["nodes"] if n["kind"] == "function")
     assert board["about"]["intent_source"] == "template"
+    assert all(n["files"] for n in board["nodes"]) and all(f["files"] for f in board["flows"])   # tags stored (spec §14.3)
 
 
 def test_ingest_failure_skips_dependent_stages(fx, tmp_path):
```

`backend/tests/test_storyboard.py`:

```diff
diff --git a/backend/tests/test_storyboard.py b/backend/tests/test_storyboard.py
index df5900d..b33f14b 100644
--- a/backend/tests/test_storyboard.py
+++ b/backend/tests/test_storyboard.py
@@ -131,7 +131,9 @@ def _board(flows=2):
                findings=["F1"], text="logger_flush → uart_send ⟶ -2 ignored", title="template title", what="template what",
                effect="e",
                check="c") for i in range(flows)]
-    return Board(flows=fl, about=About(intent="template intent"))
+    for f in fl:
+        f.files = f.what_files = ["//fixture/service/logger.c"]
+    return Board(flows=fl, about=About(intent="template intent", intent_files=["//fixture/driver/uart.c"]))
 
 
 def _respond(flow_reply):
@@ -159,6 +161,8 @@ def test_llm_writes_grounded_flow_narratives_and_the_change_intent():
         ("flush drops -2", "llm"), ("template what", "template"), ("template what", "template")]
     assert [f.title for f in board.flows] == ["logger_flush drops -2 on flush", "template title", "template title"]
     assert board.about.intent == "the change adds tx stats" and board.about.intent_source == "llm"
+    # LLM text no longer depends only on the template's files: unknown until its prompt's files are recorded
+    assert board.flows[0].what_files is None and board.about.intent_files is None
 
 
 def test_llm_calls_run_concurrently():
```

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index b81679c..8452eaa 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -253,6 +253,24 @@ def test_board_stored_by_an_older_version_gets_current_defaults(env):
     assert [f["title"] for f in b["flows"]] == ["affects uart_errors", "-2 ignored", "signature changed"]
 
 
+def test_board_stored_before_file_tags_gets_them_on_load(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    old = svc.store.get_blob(rid, "board")
+    for item in [*old["nodes"], *old["edges"], *old["impacts"], *old["layers"], *old["about"]["why"],
+                 *(f for d in old["about"]["tree"] for f in d["files"])]:
+        item.pop("files")
+    for f in old["flows"]:
+        f.pop("files"), f.pop("what_files")
+    for c in old["about"]["cls"]:
+        c["files"] = c.pop("file_count")
+    old["about"].pop("intent_files")
+    svc.store.put_blob(rid, "board", old)
+    b = owner.get(f"/api/reviews/{rid}/board").json()
+    assert all(n["files"] for n in b["nodes"]) and all(f["files"] == f["what_files"] for f in b["flows"])
+    assert [c["file_count"] for c in b["about"]["cls"]] == [1, 3] and all(c["files"] for c in b["about"]["cls"])
+
+
 def test_session_cookie_is_secure_only_when_https_is_configured(fx, tmp_path):
     from pathlib import Path
     svc = make_services(fx, tmp_path)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_provenance.py tests/test_board.py tests/test_pipeline.py tests/test_storyboard.py tests/test_web.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.provenance'` (collection stops: `1 error`)

- [ ] **Step 3: Implement**

`backend/codetortoise/board.py`:

```diff
diff --git a/backend/codetortoise/board.py b/backend/codetortoise/board.py
index e47e19c..539779f 100644
--- a/backend/codetortoise/board.py
+++ b/backend/codetortoise/board.py
@@ -25,6 +25,7 @@ from codetortoise.layers import LayerModel
 from codetortoise.vcs.model import ChangeSet
 
 Channel = Literal["contract", "signature", "state"]
+Files = list[str] | None          # depot paths an item depends on (spec §14.3); None = unknown, owner-only in stage 2
 Sev = Literal["warn", "info", "ok"]
 _RANGE_OPS = ("!=", "<", ">", "<=", ">=")
 X_SPACING = 220.0
@@ -56,6 +57,7 @@ class BoardNode(BaseModel):
     change: NodeChange | None = None
     x: float = 0.0
     warn: int = 0
+    files: Files = None
 
 
 class BoardEdge(BaseModel):
@@ -64,6 +66,7 @@ class BoardEdge(BaseModel):
     kind: str
     status: str
     confidence: str
+    files: Files = None
 
 
 class Impact(BaseModel):
@@ -78,6 +81,7 @@ class Impact(BaseModel):
     finding: str | None = None
     cause: str | None = None         # the changed node this impact comes from
     landing: bool = False            # a flow may land here (ignoring caller, field reader, signature caller)
+    files: Files = None
 
 
 class Flow(BaseModel):
@@ -94,6 +98,8 @@ class Flow(BaseModel):
     effect: str
     check: str
     what_source: Literal["template", "llm"] = "template"
+    files: Files = None
+    what_files: Files = None         # files behind `what`/`title`: the flow's own for template text, the prompt's for LLM text
 
     @model_validator(mode="after")
     def _title_from_text(self) -> Flow:
@@ -107,6 +113,7 @@ class Flow(BaseModel):
 class BoardLayer(BaseModel):
     level: int
     name: str
+    files: Files = None
 
 
 class AboutFile(BaseModel):
@@ -116,6 +123,7 @@ class AboutFile(BaseModel):
     cls: list[int]
     add: int
     rem: int
+    files: Files = None
 
 
 class AboutDir(BaseModel):
@@ -127,22 +135,46 @@ class AboutCl(BaseModel):
     cl: int
     user: str
     description: str
-    files: int
+    file_count: int
+    files: Files = None
+
+    @model_validator(mode="before")
+    @classmethod
+    def _count_was_files(cls, data):
+        """Boards stored before tags kept the file count in `files`."""
+        if isinstance(data, dict) and isinstance(data.get("files"), int):
+            data = {**data, "file_count": data["files"], "files": None}
+        return data
 
 
 class AboutWhy(BaseModel):
     severity: str
     text: str
     finding: str
+    files: Files = None
+
+
+class AboutDrift(BaseModel):
+    text: str
+    files: Files = None
+
+    @model_validator(mode="before")
+    @classmethod
+    def _from_text(cls, data):
+        """Boards stored before tags kept drift lines as "<depot> (base #a, workspace #b)" strings."""
+        if isinstance(data, str):
+            return {"text": data, "files": [data.split(" (base ", 1)[0]]}
+        return data
 
 
 class About(BaseModel):
     intent: str
     intent_source: Literal["template", "llm"] = "template"
+    intent_files: Files = None
     why: list[AboutWhy] = Field(default_factory=list)
     cls: list[AboutCl] = Field(default_factory=list)
     tree: list[AboutDir] = Field(default_factory=list)
-    drift: list[str] = Field(default_factory=list)   # base workspace differs from the CL base: context code may not match
+    drift: list[AboutDrift] = Field(default_factory=list)   # base workspace differs from the CL base: context code may not match
 
 
 class Board(BaseModel):
@@ -619,7 +651,7 @@ def build_about(c: BoardContext) -> About:
     intent = (f"{fn_count} function(s) changed in {len(files)} file(s). " + (descs + "." if descs else "")).strip()
     why = [AboutWhy(severity=f.severity, text=f.title, finding=f.id) for f in c.findings[:4]]
     cls = [AboutCl(cl=m.cl, user=m.user, description=m.description,
-                   files=sum(1 for f in files if any(p.cl == m.cl for p in f.per_cl))) for m in c.cs.cls]
+                   file_count=sum(1 for f in files if any(p.cl == m.cl for p in f.per_cl))) for m in c.cs.cls]
     prefix = _tree_prefix([f.depot for f in files])
     dirs: dict[str, list[AboutFile]] = defaultdict(list)
     for f in sorted(files, key=lambda f: f.depot):
@@ -629,5 +661,5 @@ def build_about(c: BoardContext) -> About:
         dirs[d].append(AboutFile(path=f.depot, name=posixpath.basename(rel), action=f.action,
                                  cls=[p.cl for p in f.per_cl], add=add, rem=rem))
     tree = [AboutDir(dir=d, files=fs) for d, fs in sorted(dirs.items())]
-    drift = [f"{d.depot} (base {d.expected}, workspace {d.actual})" for d in c.cs.drift]
+    drift = [AboutDrift(text=f"{d.depot} (base {d.expected}, workspace {d.actual})", files=[d.depot]) for d in c.cs.drift]
     return About(intent=intent, why=why, cls=cls, tree=tree, drift=drift)
```

`backend/codetortoise/provenance.py`:

```python
"""File tags (spec §14.3): the Perforce depot paths each visible item depends on.

`None` means unknown; stage 2 shows unknown items to the owner only. Structural tags are derived from the board itself,
so boards stored before tags existed get the same tags when they load. Tags on LLM-written text are recorded when the
text is written (the files whose code was in the prompt) and stay unknown otherwise.
"""
from __future__ import annotations

from collections.abc import Iterable

from codetortoise.board import Board, Files


def merge(*parts: Iterable[str] | None) -> Files:
    """Union of several tags, sorted; unknown if any part is unknown."""
    out: set[str] = set()
    for p in parts:
        if p is None:
            return None
        out.update(p)
    return sorted(out)


def _node_files(board: Board) -> dict[str, Files]:
    """A node's own file; a node without one (no visible definition) is named by the code that calls or reads it."""
    own: dict[str, Files] = {n.id: [n.path] if n.path else None for n in board.nodes}
    out = dict(own)
    for n in board.nodes:
        if own[n.id] is None:
            refs = [own[e.src] for e in board.edges if e.dst == n.id and own.get(e.src)]
            out[n.id] = merge(*refs) if refs else None
    return out


def tag_board(board: Board, finding_files: dict[str, Files] | None = None) -> Board:
    """Set the structural tags on every item of `board` (in place, returned for chaining). `finding_files` maps
    finding ids to their tags, for the change summary's "why it's risky" lines."""
    nf = _node_files(board)

    def of(ids: Iterable[str]) -> Files:
        return merge(*(nf.get(i) for i in ids))

    for n in board.nodes:
        n.files = nf[n.id]
    for e in board.edges:
        e.files = of([e.src, e.dst])
    for i in board.impacts:
        i.files = merge([i.path] if i.path else [], of([i.node, *([i.cause] if i.cause else [])]))
    for fl in board.flows:
        fl.files = of([*fl.path, fl.lands, *([fl.fx_at] if fl.fx_at else [])])
        if fl.what_source == "template":
            fl.what_files = fl.files
    for layer in board.layers:
        layer.files = of(n.id for n in board.nodes if n.layer == layer.level)
    tree = [f for d in board.about.tree for f in d.files]
    for f in tree:
        f.files = [f.path]
    for c in board.about.cls:
        c.files = sorted(f.path for f in tree if c.cl in f.cls) or None
    for w in board.about.why:
        w.files = (finding_files or {}).get(w.finding)
    if board.about.intent_source == "template":                     # counts and CL descriptions: every changed file
        board.about.intent_files = sorted(f.path for f in tree)
    return board
```

`backend/codetortoise/llm/storyboard.py`:

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index b606df7..f7db175 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -223,7 +223,7 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
         def describe(out: _FlowOut, fl=fl):
             # grounded: keep the LLM text only if it cites a node on this flow or one of its findings
             if out.what.strip() and set(out.cites) & (set(fl.path) | set(fl.findings)):
-                fl.what, fl.what_source = out.what.strip(), "llm"
+                fl.what, fl.what_source, fl.what_files = out.what.strip(), "llm", None
                 if 0 < len(out.title.strip()) <= 80:
                     fl.title = out.title.strip()
         jobs.append((_flow_prompt(fl, impact, findings, snippets, per_call), _FlowOut, describe))
@@ -246,7 +246,7 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
         sb.verified = any(c in known for c in out.cites)
         sb.llm_used = True
         if board is not None and out.summary.strip():
-            board.about.intent, board.about.intent_source = out.summary.strip(), "llm"
+            board.about.intent, board.about.intent_source, board.about.intent_files = out.summary.strip(), "llm", None
     except Exception as e:  # any LLM-side failure leaves the deterministic storyboard intact
         sb.llm_error = str(e) if isinstance(e, LlmError) else f"{type(e).__name__}: {e}"
     finally:
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index bbd425d..2045a86 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -15,6 +15,7 @@ from codetortoise.facts.runner import build_requests, run_extraction
 from codetortoise.impact import ImpactModel, build_impact
 from codetortoise.llm.storyboard import build_storyboard
 from codetortoise.paths import canon
+from codetortoise.provenance import tag_board
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
 from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
@@ -191,8 +192,9 @@ def run_review(rid: int, svc: Services) -> None:
     def board():
         notes: list[str] = []
         resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
-        b = build_board(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
-                                     ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root))))
+        b = tag_board(build_board(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"],
+                                               ctx["findings"], ctx.get("layers"), cfg.analysis, resolve,
+                                               root=canon(str(cfg.workspace.root)))))
         ctx["board"] = b
         store.put_blob(rid, "board", b)
         if notes:
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index e08f688..8489ef6 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -13,6 +13,7 @@ from pydantic import BaseModel, Field
 from codetortoise.board import Board
 from codetortoise.health import run_health
 from codetortoise.pipeline import JobRunner
+from codetortoise.provenance import tag_board
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
 from codetortoise.vcs.p4runner import P4Error
@@ -171,7 +172,8 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         b = store.get_blob(rid, "board")
         if b is None:
             raise HTTPException(404, "board not built yet")
-        b = Board.model_validate(b).model_dump()          # boards stored by an older version get current defaults
+        # boards stored by an older version get current defaults and file tags (spec §14.3)
+        b = tag_board(Board.model_validate(b)).model_dump()
         overrides = store.kv_get("layer_overrides") or {}
         for layer in b.get("layers", []):
             if str(layer["level"]) in overrides:
```

`frontend/src/board/types.ts`:

```diff
diff --git a/frontend/src/board/types.ts b/frontend/src/board/types.ts
index 0ffbb35..45b0633 100644
--- a/frontend/src/board/types.ts
+++ b/frontend/src/board/types.ts
@@ -21,9 +21,9 @@ export interface AboutFile { path: string; name: string; action: string; cls: nu
 export interface About {
   intent: string; intent_source: "template" | "llm";
   why: { severity: string; text: string; finding: string }[];
-  cls: { cl: number; user: string; description: string; files: number }[];
+  cls: { cl: number; user: string; description: string; file_count: number }[];
   tree: { dir: string; files: AboutFile[] }[];
-  drift: string[];
+  drift: { text: string }[];
 }
 export interface Board {
   nodes: BoardNode[]; edges: BoardEdge[]; flows: BoardFlow[]; impacts: Annotation[];
```

`frontend/src/board/ChangePanel.tsx`:

```diff
diff --git a/frontend/src/board/ChangePanel.tsx b/frontend/src/board/ChangePanel.tsx
index 6052257..07e55a3 100644
--- a/frontend/src/board/ChangePanel.tsx
+++ b/frontend/src/board/ChangePanel.tsx
@@ -53,7 +53,7 @@ export default function ChangePanel({ open, onToggle, reviewId, comments, onComm
         {about.drift.length > 0 && (
           <div className="bd-drift">
             ⚠ The base workspace is not at the changelists' base revision, so context code fetched from it may not match
-            what was analysed: {about.drift.join("; ")}
+            what was analysed: {about.drift.map((d) => d.text).join("; ")}
           </div>
         )}
         <h3>Files in this change</h3>
@@ -116,7 +116,7 @@ export default function ChangePanel({ open, onToggle, reviewId, comments, onComm
           ))}
         <h3>Changelists</h3>
         {about.cls.map((c) => (
-          <div key={c.cl} className="cl"><span className="n">CL {c.cl}</span> <span className="m">· {c.user} · {c.files} files</span>
+          <div key={c.cl} className="cl"><span className="n">CL {c.cl}</span> <span className="m">· {c.user} · {c.file_count} files</span>
             <div className="desc">{c.description}</div></div>
         ))}
       </div>
```

`frontend/src/pages/Review.tsx`:

```diff
diff --git a/frontend/src/pages/Review.tsx b/frontend/src/pages/Review.tsx
index ae9c135..de2ed73 100644
--- a/frontend/src/pages/Review.tsx
+++ b/frontend/src/pages/Review.tsx
@@ -73,7 +73,7 @@ export default function Review() {
       </nav>
       {me?.is_owner && ready && <button className="link rerun" onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button>}
       {board && board.about.drift.length > 0 && (
-        <span className="bd-pill high" title={board.about.drift.join("\n")}>⚠ workspace drift ({board.about.drift.length})</span>
+        <span className="bd-pill high" title={board.about.drift.map((d) => d.text).join("\n")}>⚠ workspace drift ({board.about.drift.length})</span>
       )}
       {notes.length > 0 && (
         <details className="bd-notes">
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_provenance.py tests/test_board.py tests/test_pipeline.py tests/test_storyboard.py tests/test_web.py -q`
Expected: `81 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q && cd ../frontend && npx vitest run && npx tsc --noEmit`
Expected: `All checks passed!`, `210 passed`, `Tests  69 passed (69)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/board.py backend/codetortoise/provenance.py backend/codetortoise/llm/storyboard.py backend/codetortoise/pipeline.py backend/codetortoise/web/app.py frontend/src/board/types.ts frontend/src/board/ChangePanel.tsx frontend/src/pages/Review.tsx backend/tests/test_provenance.py backend/tests/test_board.py backend/tests/test_pipeline.py backend/tests/test_storyboard.py backend/tests/test_web.py
git commit -m "feat(board): file tags on every board item and the change summary"
```

---

### Task 5: File tags on findings

Spec §14.3. Findings and LLM prompts name graph nodes that are not all on the board, so the board stage also resolves
every impact-graph node's file and every evidence file in one more batched lookup (`depot_resolver` now asks Perforce
about each workspace file once, found or not). `local_files` turns workspace paths into tags: the depot path, `[]`
outside the workspace (not under Perforce), unknown when the lookup failed. `impact_node_files` gives a node without a
file (a field) the files of the nodes that access it. A finding's `files` are its nodes' and its evidence's; the stored
findings and the board's "why it's risky" lines carry them, and `/board` passes the stored findings' tags.

**Files:**
- Modify: `backend/codetortoise/detectors/base.py`
- Modify: `backend/codetortoise/provenance.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/web/app.py`
- Modify: `backend/tests/test_provenance.py`
- Modify: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `merge`, `tag_board` (Task 4).
- Produces: `Finding.files`, `Finding.explain_files` (`list[str] | None`); `provenance.local_files(locals_, resolved,
  root) -> dict[str, Files]`; `provenance.impact_node_files(impact, by_local) -> dict[str, Files]`;
  `provenance.finding_files(f, node_files, by_local) -> Files`; pipeline `ctx["node_files"]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_provenance.py`:

```diff
diff --git a/backend/tests/test_provenance.py b/backend/tests/test_provenance.py
index c263e3c..2812b5a 100644
--- a/backend/tests/test_provenance.py
+++ b/backend/tests/test_provenance.py
@@ -71,3 +71,41 @@ def test_boards_stored_before_tags_load_with_counts_and_drift_migrated():
     b = tag_board(Board.model_validate(old))
     assert b.about.cls[0].file_count == 1 and b.about.cls[0].files == ["//d/a.c"]
     assert b.about.drift[0].text == "//d/a.c (base #3, workspace #4)" and b.about.drift[0].files == ["//d/a.c"]
+
+
+def test_local_files_resolve_through_perforce_and_skip_paths_outside_the_workspace():
+    from codetortoise.provenance import local_files
+    got = local_files(["/ws/a.c", "/ws/b.c", "/usr/include/stdio.h"], {"/ws/a.c": "//d/a.c"}, "/ws")
+    assert got == {"/ws/a.c": ["//d/a.c"], "/ws/b.c": None, "/usr/include/stdio.h": []}   # not under Perforce: no tag
+
+
+def _impact():
+    from codetortoise.impact import Edge, ImpactModel, Node
+    nodes = {"N1": Node(id="N1", key="set", label="set", file="/ws/a.c", line=1, status="changed"),
+             "N2": Node(id="N2", key="field:R::v", kind="field", label="R::v"),         # no file: named by its accessors
+             "N3": Node(id="N3", key="peek", label="peek", file="/ws/b.c", line=20),
+             "N4": Node(id="N4", key="printf", label="printf", file="/usr/include/stdio.h", line=9),
+             "N5": Node(id="N5", key="lost", label="lost", file="/ws/lost.c", line=3)}      # lookup failed: unknown
+    edges = [Edge(id="E1", src="N1", dst="N2", kind="writes"), Edge(id="E2", src="N3", dst="N2", kind="reads"),
+             Edge(id="E3", src="N3", dst="N1", kind="call"), Edge(id="E4", src="N1", dst="N4", kind="call")]
+    return ImpactModel(nodes=nodes, edges=edges, changed=["N1"])
+
+
+def test_graph_nodes_take_their_files_or_their_accessors_files():
+    from codetortoise.provenance import impact_node_files, local_files
+    by_local = local_files(["/ws/a.c", "/ws/b.c", "/usr/include/stdio.h", "/ws/lost.c"],
+                           {"/ws/a.c": "//d/a.c", "/ws/b.c": "//d/b.c"}, "/ws")
+    assert impact_node_files(_impact(), by_local) == {
+        "N1": ["//d/a.c"], "N2": ["//d/a.c", "//d/b.c"], "N3": ["//d/b.c"], "N4": [], "N5": None}
+
+
+def test_a_finding_depends_on_its_nodes_and_its_evidence():
+    from codetortoise.detectors.base import Evidence, Finding
+    from codetortoise.provenance import finding_files
+    nf = {"N1": ["//d/a.c"], "N5": None}
+    by_local = {"/ws/b.c": ["//d/b.c"], "/usr/include/stdio.h": []}
+    f = Finding(kind="k", severity="high", title="t", summary="s", nodes=["N1"],
+                evidence=[Evidence(text="e", file="/ws/b.c", line=2), Evidence(text="sys", file="/usr/include/stdio.h")])
+    assert finding_files(f, nf, by_local) == ["//d/a.c", "//d/b.c"]
+    assert finding_files(f.model_copy(update={"nodes": ["N1", "N5"]}), nf, by_local) is None
+    assert Finding(kind="k", severity="low", title="t", summary="s").files is None        # stored before tags: unknown
```

`backend/tests/test_pipeline.py`:

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 3cb1d59..0a2ce08 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -30,6 +30,10 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
     assert all(n["path"].startswith("//fixture/") for n in board["nodes"] if n["kind"] == "function")
     assert board["about"]["intent_source"] == "template"
     assert all(n["files"] for n in board["nodes"]) and all(f["files"] for f in board["flows"])   # tags stored (spec §14.3)
+    findings = {f.id: f for f in svc.store.list_findings(rid)}
+    assert all(f.files for f in findings.values())
+    assert "//fixture/driver/uart.c" in findings["F1"].files
+    assert [w["files"] for w in board["about"]["why"]] == [findings[w["finding"]].files for w in board["about"]["why"]]
 
 
 def test_ingest_failure_skips_dependent_stages(fx, tmp_path):
@@ -212,6 +216,13 @@ def test_board_without_depot_paths_for_context_nodes_is_degraded(fx, tmp_path):
     paths = {n["label"]: n["path"] for n in board["nodes"]}
     assert paths["uart_send"] == "//fixture/driver/uart.c" and paths["main"] is None
     assert len(board["flows"]) == 3
+    # the files Perforce could not name are unknown, never guessed (spec §14.3)
+    tags = {n["label"]: n["files"] for n in board["nodes"]}
+    assert tags["uart_send"] == ["//fixture/driver/uart.c"] and tags["main"] is None
+    assert all(f["files"] is None for f in board["flows"])                    # every flow starts at main
+    f5 = next(f for f in svc.store.list_findings(rid) if f.id == "F5")      # evidence in service/logger.c
+    assert f5.files is None
+    assert st["board"]["message"].count("connect failed") == 1              # one lookup, not one per caller
 
 
 def test_depot_resolver_asks_the_source_only_about_workspace_files():
@@ -229,6 +240,8 @@ def test_depot_resolver_asks_the_source_only_about_workspace_files():
     got = resolve(["/ws/a.c", "/ws/b/c.h", "/usr/include/stdio.h", "/wsx/d.c"])
     assert got == {"/ws/a.c": "//d/a.c", "/ws/b/c.h": "//d/b/c.h"}
     assert asked == [["/ws/b/c.h"]] and notes == []
+    assert resolve(["/ws/b/c.h", "/ws/e.c"]) == {"/ws/b/c.h": "//d/b/c.h", "/ws/e.c": "//d/e.c"}
+    assert asked == [["/ws/b/c.h"], ["/ws/e.c"]]                       # each workspace file is asked about once
 
 
 def test_depot_resolver_failure_keeps_changed_files_and_notes_why():
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_provenance.py tests/test_pipeline.py -q`
Expected: FAIL — `6 failed, 17 passed` (`ImportError: cannot import name 'impact_node_files'`, `AttributeError: 'Finding' object has no attribute 'files'`, the resolver asks twice)

- [ ] **Step 3: Implement**

`backend/codetortoise/detectors/base.py`:

```diff
diff --git a/backend/codetortoise/detectors/base.py b/backend/codetortoise/detectors/base.py
index 279cb3f..5a6131f 100644
--- a/backend/codetortoise/detectors/base.py
+++ b/backend/codetortoise/detectors/base.py
@@ -41,6 +41,8 @@ class Finding(BaseModel):
     verify_steps: list[str] = Field(default_factory=list)
     hypotheses: list[Hypothesis] = Field(default_factory=list)
     state: Literal["open", "ack", "dismissed"] = "open"
+    files: list[str] | None = None          # depot paths behind the finding (spec §14.3); None = unknown
+    explain_files: list[str] | None = None  # files behind the LLM explanation, verify steps and hypotheses
 
 
 @dataclass
```

`backend/codetortoise/provenance.py`:

```diff
diff --git a/backend/codetortoise/provenance.py b/backend/codetortoise/provenance.py
index 976f23a..6dc74fe 100644
--- a/backend/codetortoise/provenance.py
+++ b/backend/codetortoise/provenance.py
@@ -9,6 +9,9 @@ from __future__ import annotations
 from collections.abc import Iterable
 
 from codetortoise.board import Board, Files
+from codetortoise.detectors.base import Finding
+from codetortoise.impact import ImpactModel
+from codetortoise.paths import canon
 
 
 def merge(*parts: Iterable[str] | None) -> Files:
@@ -62,3 +65,27 @@ def tag_board(board: Board, finding_files: dict[str, Files] | None = None) -> Bo
     if board.about.intent_source == "template":                     # counts and CL descriptions: every changed file
         board.about.intent_files = sorted(f.path for f in tree)
     return board
+
+
+def local_files(locals_: Iterable[str], resolved: dict[str, str], root: str) -> dict[str, Files]:
+    """Workspace paths to tags: the depot path Perforce gave; `[]` outside the workspace (not under Perforce, e.g.
+    system headers); unknown when a workspace file could not be looked up."""
+    prefix = canon(str(root)).rstrip("/") + "/"
+    return {p: [resolved[p]] if p in resolved else ([] if not p.startswith(prefix) else None) for p in locals_}
+
+
+def impact_node_files(impact: ImpactModel, by_local: dict[str, Files]) -> dict[str, Files]:
+    """Tags for every node of the impact graph: its file; a node without one is named by the code that accesses it."""
+    own: dict[str, Files] = {nid: by_local.get(n.file) if n.file else None for nid, n in impact.nodes.items()}
+    out = dict(own)
+    for nid, n in impact.nodes.items():
+        if n.file is None:
+            refs = [own[e.src] for e in impact.edges if e.dst == nid and own.get(e.src)]
+            out[nid] = merge(*refs) if refs else None
+    return out
+
+
+def finding_files(f: Finding, node_files: dict[str, Files], by_local: dict[str, Files]) -> Files:
+    """A finding's nodes' files and the files its evidence points at."""
+    return merge(*(node_files.get(n) for n in f.nodes),
+                 *(by_local.get(e.file) if e.file else [] for e in f.evidence))
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 2045a86..82463f1 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -15,7 +15,7 @@ from codetortoise.facts.runner import build_requests, run_extraction
 from codetortoise.impact import ImpactModel, build_impact
 from codetortoise.llm.storyboard import build_storyboard
 from codetortoise.paths import canon
-from codetortoise.provenance import tag_board
+from codetortoise.provenance import finding_files, impact_node_files, local_files, tag_board
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
 from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
@@ -63,10 +63,13 @@ def depot_resolver(source, cs: ChangeSet, root: str, notes: list[str]):
     leaves those nodes without a depot path (no context code on demand for them)."""
     prefix = canon(str(root)).rstrip("/") + "/"
 
+    known = {f.local: f.depot for f in cs.files}
+    asked: set[str] = set()                 # each workspace file is looked up once, found or not
+
     def resolve(locals_: list[str]) -> dict[str, str]:
-        known = {f.local: f.depot for f in cs.files}
-        rest = sorted({p for p in locals_ if p not in known and p.startswith(prefix)})
+        rest = sorted({p for p in locals_ if p not in known and p not in asked and p.startswith(prefix)})
         if rest:
+            asked.update(rest)
             try:
                 known.update(source.depots_for(rest))
             except Exception as e:  # board still useful without depot paths for context nodes
@@ -192,9 +195,18 @@ def run_review(rid: int, svc: Services) -> None:
     def board():
         notes: list[str] = []
         resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
-        b = tag_board(build_board(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"],
-                                               ctx["findings"], ctx.get("layers"), cfg.analysis, resolve,
-                                               root=canon(str(cfg.workspace.root)))))
+        b = build_board(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
+                                     ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root))))
+        # file tags (spec §14.3): every graph node and finding, from one more lookup of the files not yet resolved
+        findings, im = ctx["findings"], ctx["impact"]
+        locals_ = sorted({n.file for n in im.nodes.values() if n.file} | {e.file for f in findings for e in f.evidence if e.file})
+        by_local = local_files(locals_, resolve(locals_), str(cfg.workspace.root))
+        node_files = impact_node_files(im, by_local)
+        for f in findings:
+            f.files = finding_files(f, node_files, by_local)
+        store.put_findings(rid, findings)
+        ctx["node_files"], ctx["local_files"] = node_files, by_local
+        b = tag_board(b, {f.id: f.files for f in findings})
         ctx["board"] = b
         store.put_blob(rid, "board", b)
         if notes:
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 8489ef6..fcafcbc 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -173,7 +173,7 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         if b is None:
             raise HTTPException(404, "board not built yet")
         # boards stored by an older version get current defaults and file tags (spec §14.3)
-        b = tag_board(Board.model_validate(b)).model_dump()
+        b = tag_board(Board.model_validate(b), {f.id: f.files for f in store.list_findings(rid)}).model_dump()
         overrides = store.kv_get("layer_overrides") or {}
         for layer in b.get("layers", []):
             if str(layer["level"]) in overrides:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_provenance.py tests/test_pipeline.py -q`
Expected: `23 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `213 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/detectors/base.py backend/codetortoise/provenance.py backend/codetortoise/pipeline.py backend/codetortoise/web/app.py backend/tests/test_provenance.py backend/tests/test_pipeline.py
git commit -m "feat(findings): file tags on findings, from every graph node's depot file"
```

---

### Task 6: Tags on AI-written text

Spec §14.3. `build_storyboard` takes the graph's `node_files` and records, as each LLM reply is applied, the files whose
code or findings were in that prompt: a flow's steps and findings (`what_files`), a finding's nodes, their neighbours
and its own files (`explain_files`), every chapter's nodes and findings plus the first 30 findings for the intent
(`intent_files`). Any unknown input makes the tag unknown. Because LLM flow text stands in for the flow's own text,
`tag_board` also adds the flow's `files` to an LLM `what_files`. The pipeline passes `node_files` and re-tags the board
it stores after the LLM stage.

**Files:**
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/provenance.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/tests/test_storyboard.py`
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/tests/test_provenance.py`

**Interfaces:**
- Consumes: `merge`, `tag_board` (Task 4); `Finding.files`, `ctx["node_files"]` (Task 5).
- Produces: `build_storyboard(..., node_files: dict[str, list[str] | None] | None = None)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_storyboard.py`:

```diff
diff --git a/backend/tests/test_storyboard.py b/backend/tests/test_storyboard.py
index b33f14b..4b74a3f 100644
--- a/backend/tests/test_storyboard.py
+++ b/backend/tests/test_storyboard.py
@@ -165,6 +165,32 @@ def test_llm_writes_grounded_flow_narratives_and_the_change_intent():
     assert board.flows[0].what_files is None and board.about.intent_files is None
 
 
+def test_llm_text_records_the_files_behind_its_prompt():
+    im, findings, layers = model()
+    findings[0].files, findings[1].files = ["//w/d/uart.c"], ["//w/include/hal/regs.h"]
+    node_files = {"N1": ["//w/hal/regs.c"], "N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]}
+    board = _board(1)
+    build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: {"what": "flush drops -2", "cites": ["N3"]})),
+                     board=board, node_files=node_files)
+    # the flow's prompt: its steps (N3, N2) and its finding F1
+    assert board.flows[0].what_source == "llm" and board.flows[0].what_files == ["//w/d/uart.c", "//w/svc/logger.c"]
+    # a finding's explanation also saw its nodes' neighbours (N3 calls N2, N2 calls N1)
+    assert findings[0].explain_files == ["//w/d/uart.c", "//w/hal/regs.c", "//w/svc/logger.c"]
+    assert findings[1].explain_files == ["//w/include/hal/regs.h"]
+    # the intent summarises every chapter (its nodes and findings) and the findings
+    assert board.about.intent_files == ["//w/d/uart.c", "//w/hal/regs.c", "//w/include/hal/regs.h"]
+
+
+def test_llm_text_is_unknown_when_a_prompt_file_is():
+    im, findings, layers = model()
+    findings[0].files = None                                   # F1 stored before tags
+    findings[1].files = ["//w/include/hal/regs.h"]
+    board = _board(1)
+    build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: {"what": "w", "cites": ["N3"]})),
+                     board=board, node_files={"N1": ["//w/hal/regs.c"], "N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]})
+    assert board.flows[0].what_files is None and findings[0].explain_files is None and board.about.intent_files is None
+    assert findings[1].explain_files == ["//w/include/hal/regs.h"]
+
 def test_llm_calls_run_concurrently():
     import threading
     im, findings, layers = model()
```

`backend/tests/test_pipeline.py`:

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 0a2ce08..21bc96f 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -129,6 +129,31 @@ def test_malformed_llm_reply_still_stores_storyboard(fx, tmp_path):
     assert sb is not None and sb["risk"] == "high" and "unexpected LLM response" in sb["llm_error"]
 
 
+def test_llm_text_stored_by_a_review_records_its_prompt_files(fx, tmp_path):
+    import json
+
+    import httpx
+
+    from codetortoise.llm.client import LlmClient
+    cites = [f"N{i}" for i in range(1, 40)] + [f"F{i}" for i in range(1, 10)]
+
+    def reply(req):
+        user = json.loads(req.content)["messages"][1]["content"]
+        out = ({"explanation": "e"} if "Explain the risk" in user else
+               {"narrative": "n", "cites": cites} if "narrative for this architectural layer" in user else
+               {"what": "w", "title": "t", "cites": cites} if "Describe this call flow" in user else
+               {"summary": "s", "risk": "high", "cites": cites})
+        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}}]})
+    llm = LlmClient("http://llm/v1", "k", "m", sleep=lambda s: None, transport=httpx.MockTransport(reply))
+    svc = make_services(fx, tmp_path, llm=llm)
+    rid = svc.store.create_review("t", "owner", [101, 102])
+    run_review(rid, svc)
+    board = svc.store.get_blob(rid, "board")
+    assert board["about"]["intent_source"] == "llm" and board["about"]["intent_files"]
+    llm_flows = [f for f in board["flows"] if f["what_source"] == "llm"]
+    assert llm_flows and all(f["what_files"] and set(f["files"]) <= set(f["what_files"]) for f in llm_flows)
+    assert all(f.explain_files and set(f.files) <= set(f.explain_files) for f in svc.store.list_findings(rid))
+
 class WarningSource:
     def __init__(self, inner):
         self.inner = inner
```

`backend/tests/test_provenance.py`:

```diff
diff --git a/backend/tests/test_provenance.py b/backend/tests/test_provenance.py
index 2812b5a..31cf95b 100644
--- a/backend/tests/test_provenance.py
+++ b/backend/tests/test_provenance.py
@@ -59,8 +59,9 @@ def test_llm_text_keeps_its_recorded_files_and_is_unknown_when_none_were_recorde
     b.flows[0].what_source = "llm"
     tagged = tag_board(b.model_copy(deep=True))
     assert tagged.flows[0].what_files is None and tagged.about.intent_files is None
-    b.flows[0].what_files, b.about.intent_files = ["//d/a.c", "//d/z.c"], ["//d/a.c"]
+    b.flows[0].what_files, b.about.intent_files = ["//d/z.c"], ["//d/a.c"]
     tagged = tag_board(b)
+    # LLM text stands in for the flow's own text, so it also carries the flow's files
     assert tagged.flows[0].what_files == ["//d/a.c", "//d/z.c"] and tagged.about.intent_files == ["//d/a.c"]
 
 
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_pipeline.py tests/test_provenance.py -q`
Expected: FAIL — `4 failed, 33 passed` (`TypeError: build_storyboard() got an unexpected keyword argument 'node_files'`, an LLM `what_files` without the flow's files)

- [ ] **Step 3: Implement**

`backend/codetortoise/llm/storyboard.py`:

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index f7db175..259e0f8 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -12,6 +12,7 @@ from codetortoise.detectors.base import SEVERITY_RANK, Finding, Hypothesis
 from codetortoise.impact import ImpactModel
 from codetortoise.layers import LayerModel
 from codetortoise.llm.client import LlmClient, LlmError
+from codetortoise.provenance import merge
 
 SYSTEM = ("You are a senior C/C++ code reviewer. You are given facts extracted by static analysis "
           "for a set of changes. Use ONLY these facts. Refer to functions/fields by their node id (e.g. N3) "
@@ -179,11 +180,19 @@ def _flow_prompt(fl: Flow, impact: ImpactModel, findings: list[Finding], snippet
 
 def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: LayerModel | None,
                      snippets: dict[str, str], llm: LlmClient | None, max_tokens: int = 64000, *,
-                     board: Board | None = None, concurrency: int = 1, max_flow_narratives: int = 6) -> Storyboard:
+                     board: Board | None = None, concurrency: int = 1, max_flow_narratives: int = 6,
+                     node_files: dict[str, list[str] | None] | None = None) -> Storyboard:
     """Skeleton storyboard, then (with an LLM) finding explanations, chapter and flow narratives on a thread pool.
 
     Results are applied in a fixed order, so the output depends only on the replies; the summary call runs last.
-    Any LLM-side failure keeps the deterministic text for everything not yet applied."""
+    Any LLM-side failure keeps the deterministic text for everything not yet applied. LLM text records the files whose
+    code or findings were in its prompt (spec §14.3), from `node_files`; without it they stay unknown."""
+    tags = {f.id: f.files for f in findings}
+
+    def prompt_files(nodes: list[str], finding_ids: list[str]) -> list[str] | None:
+        if node_files is None:
+            return None
+        return merge(*(node_files.get(n) for n in nodes), *(tags.get(i) for i in finding_ids))
     sb = skeleton(impact, findings, layers)
     if llm is None:
         return sb
@@ -198,8 +207,8 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
         parts = ["FINDING:\n" + _finding_text(f), "GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes + neighbours)]
         parts += [f"CODE {n}:\n{snippets[n]}" for n in nodes + neighbours if n in snippets]
 
-        def explain(out: _ExplainOut, f=f):
-            f.explanation = out.explanation
+        def explain(out: _ExplainOut, f=f, seen=nodes + neighbours):
+            f.explanation, f.explain_files = out.explanation, prompt_files(seen, [f.id])
             f.verify_steps = out.verify_steps
             f.hypotheses = [Hypothesis(text=h.text, cites=h.cites) for h in ground(out.hypotheses, known)]
         jobs.append(("Explain the risk of this finding, list concrete verification steps, and propose additional "
@@ -223,7 +232,7 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
         def describe(out: _FlowOut, fl=fl):
             # grounded: keep the LLM text only if it cites a node on this flow or one of its findings
             if out.what.strip() and set(out.cites) & (set(fl.path) | set(fl.findings)):
-                fl.what, fl.what_source, fl.what_files = out.what.strip(), "llm", None
+                fl.what, fl.what_source, fl.what_files = out.what.strip(), "llm", prompt_files(fl.path, fl.findings)
                 if 0 < len(out.title.strip()) <= 80:
                     fl.title = out.title.strip()
         jobs.append((_flow_prompt(fl, impact, findings, snippets, per_call), _FlowOut, describe))
@@ -246,7 +255,9 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
         sb.verified = any(c in known for c in out.cites)
         sb.llm_used = True
         if board is not None and out.summary.strip():
-            board.about.intent, board.about.intent_source, board.about.intent_files = out.summary.strip(), "llm", None
+            board.about.intent, board.about.intent_source = out.summary.strip(), "llm"
+            board.about.intent_files = merge(*(prompt_files(c.nodes, c.findings) for c in sb.chapters),
+                                             prompt_files([], [f.id for f in findings[:30]]))
     except Exception as e:  # any LLM-side failure leaves the deterministic storyboard intact
         sb.llm_error = str(e) if isinstance(e, LlmError) else f"{type(e).__name__}: {e}"
     finally:
```

`backend/codetortoise/provenance.py`:

```diff
diff --git a/backend/codetortoise/provenance.py b/backend/codetortoise/provenance.py
index 6dc74fe..e4dcf57 100644
--- a/backend/codetortoise/provenance.py
+++ b/backend/codetortoise/provenance.py
@@ -53,6 +53,8 @@ def tag_board(board: Board, finding_files: dict[str, Files] | None = None) -> Bo
         fl.files = of([*fl.path, fl.lands, *([fl.fx_at] if fl.fx_at else [])])
         if fl.what_source == "template":
             fl.what_files = fl.files
+        elif fl.what_files is not None:                              # LLM text stands in for the flow's own text
+            fl.what_files = merge(fl.what_files, fl.files)
     for layer in board.layers:
         layer.files = of(n.id for n in board.nodes if n.layer == layer.level)
     tree = [f for d in board.about.tree for f in d.files]
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 82463f1..d2e4f9f 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -219,11 +219,11 @@ def run_review(rid: int, svc: Services) -> None:
         b = ctx.get("board")
         sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
                               board=b, concurrency=cfg.llm.concurrency,
-                              max_flow_narratives=cfg.llm.max_flow_narratives)
+                              max_flow_narratives=cfg.llm.max_flow_narratives, node_files=ctx.get("node_files"))
         store.put_findings(rid, findings)
         store.put_blob(rid, "storyboard", sb)
         if b is not None:
-            store.put_blob(rid, "board", b)
+            store.put_blob(rid, "board", tag_board(b, {f.id: f.files for f in findings}))
         ctx["storyboard"] = sb
         if svc.llm is None:
             raise Degraded("no LLM configured; deterministic storyboard only")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_pipeline.py tests/test_provenance.py -q`
Expected: `37 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `216 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/llm/storyboard.py backend/codetortoise/provenance.py backend/codetortoise/pipeline.py backend/tests/test_storyboard.py backend/tests/test_pipeline.py backend/tests/test_provenance.py
git commit -m "feat(llm): AI-written text records the files behind its prompt"
```

---

### Task 7: Comment scope, and the spec as built

Spec §14.3. Comments store no tags; `comment_scope` derives what the author was looking at from the anchor: a line's
file (`path`, or `depot` for M1 anchors), a function's board node, a finding by kind and title (plus its explanation's
files once explained), a layer, or for a review-level comment every tag on the board and the findings
(`review_files`). Unknown anywhere makes the scope unknown. Stage 2 will filter with it; stage 1 only provides it. The
spec's §14 is brought in line with the code as built.

**Files:**
- Modify: `backend/codetortoise/provenance.py`
- Modify: `docs/superpowers/specs/2026-10-01-review-board-design.md`
- Modify: `backend/tests/test_provenance.py`

**Interfaces:**
- Consumes: `merge` (Task 4); `Finding.files`, `Finding.explain_files` (Task 5).
- Produces: `provenance.comment_scope(board, findings, anchor_kind, anchor) -> Files`;
  `provenance.review_files(board, findings) -> Files`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_provenance.py`:

```diff
diff --git a/backend/tests/test_provenance.py b/backend/tests/test_provenance.py
index 31cf95b..d10edd5 100644
--- a/backend/tests/test_provenance.py
+++ b/backend/tests/test_provenance.py
@@ -110,3 +110,27 @@ def test_a_finding_depends_on_its_nodes_and_its_evidence():
     assert finding_files(f, nf, by_local) == ["//d/a.c", "//d/b.c"]
     assert finding_files(f.model_copy(update={"nodes": ["N1", "N5"]}), nf, by_local) is None
     assert Finding(kind="k", severity="low", title="t", summary="s").files is None        # stored before tags: unknown
+
+
+def test_comment_scope_follows_the_anchor(board):  # noqa: F811
+    from codetortoise.detectors.base import Finding
+    from codetortoise.provenance import comment_scope
+    why = {"F1": [D + "driver/uart.c"], "F2": [D + "include/hal/regs.h"], "F3": [D + "driver/uart.h"],
+           "F4": [D + "hal/regs.c"]}
+    b = tag_board(board.model_copy(deep=True), why)
+    finding = Finding(id="F1", kind="field_mutation", severity="high", title="uart_send now writes Uart::errors",
+                      summary="s", explanation="e", files=[D + "driver/uart.c"],
+                      explain_files=[D + "driver/uart.c", D + "service/logger.c"])
+    scope = lambda kind, anchor: comment_scope(b, [finding], kind, anchor)  # noqa: E731
+    assert scope("line", {"path": D + "service/logger.c", "side": "new", "line": 21}) == [D + "service/logger.c"]
+    assert scope("line", {"depot": D + "app/main.c", "cl": 101, "side": "new", "line": 3}) == [D + "app/main.c"]  # M1 shape
+    assert scope("function", {"key": next(n.key for n in b.nodes if n.label == "uart_errors")}) == [D + "driver/uart.c"]
+    assert scope("function", {"key": "c:@F@not_on_the_board"}) is None
+    assert scope("finding", {"kind": "field_mutation", "title": "uart_send now writes Uart::errors"}) == \
+        [D + "driver/uart.c", D + "service/logger.c"]                   # what its readers saw, explanation included
+    assert scope("chapter", {"level": 2}) == [D + "driver/uart.c", D + "driver/uart.h"]
+    everything = scope("review", {})
+    assert set(everything) >= {f.path for d in b.about.tree for f in d.files} | {n.path for n in b.nodes}
+    assert scope("line", {}) is None
+    unknown_why = tag_board(board.model_copy(deep=True), {"F1": [D + "driver/uart.c"]})   # F2-F4 unknown
+    assert comment_scope(unknown_why, [finding], "review", {}) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_provenance.py -q`
Expected: FAIL — `1 failed, 9 passed` — `ImportError: cannot import name 'comment_scope'`

- [ ] **Step 3: Implement**

`backend/codetortoise/provenance.py`:

```diff
diff --git a/backend/codetortoise/provenance.py b/backend/codetortoise/provenance.py
index e4dcf57..75a83ab 100644
--- a/backend/codetortoise/provenance.py
+++ b/backend/codetortoise/provenance.py
@@ -91,3 +91,29 @@ def finding_files(f: Finding, node_files: dict[str, Files], by_local: dict[str,
     """A finding's nodes' files and the files its evidence points at."""
     return merge(*(node_files.get(n) for n in f.nodes),
                  *(by_local.get(e.file) if e.file else [] for e in f.evidence))
+
+
+def comment_scope(board: Board, findings: list[Finding], anchor_kind: str, anchor: dict) -> Files:
+    """The files a comment depends on, from where it is anchored (not stored): what its author was looking at."""
+    if anchor_kind == "line":
+        path = anchor.get("path") or anchor.get("depot")             # M1 line anchors used `depot`
+        return [path] if path else None
+    if anchor_kind == "function":
+        return next((n.files for n in board.nodes if n.key == anchor.get("key")), None)
+    if anchor_kind == "finding":
+        f = next((f for f in findings if f.kind == anchor.get("kind") and f.title == anchor.get("title")), None)
+        return merge(f.files, f.explain_files if f.explanation else []) if f else None
+    if anchor_kind == "chapter":
+        return next((layer.files for layer in board.layers if layer.level == anchor.get("level")), None)
+    if anchor_kind == "review":
+        return review_files(board, findings)
+    return None
+
+
+def review_files(board: Board, findings: list[Finding]) -> Files:
+    """Every file behind anything shown for the review: the board, the change summary and the findings."""
+    a = board.about
+    tags = [*(i.files for i in [*board.nodes, *board.edges, *board.impacts, *board.layers, *a.cls, *a.why, *a.drift]),
+            *(f.files for d in a.tree for f in d.files), *(t for fl in board.flows for t in (fl.files, fl.what_files)),
+            a.intent_files, *(f.files for f in findings), *(f.explain_files for f in findings if f.explanation)]
+    return merge(*tags)
```

`docs/superpowers/specs/2026-10-01-review-board-design.md`:

```diff
diff --git a/docs/superpowers/specs/2026-10-01-review-board-design.md b/docs/superpowers/specs/2026-10-01-review-board-design.md
index ee54c68..841b3f5 100644
--- a/docs/superpowers/specs/2026-10-01-review-board-design.md
+++ b/docs/superpowers/specs/2026-10-01-review-board-design.md
@@ -456,8 +456,8 @@ rest, HTTPS enforcement.
 ### 14.2 Plain HTTP on the network: warn, don't refuse
 
 - **Optional HTTPS:** `server.tls_cert` and `server.tls_key` (paths). When both are set, uvicorn serves HTTPS with them
-  and the session cookie gets `Secure`. When only one is set, startup fails with a config error. Plain HTTP stays
-  allowed.
+  and the session cookie gets `Secure`. When only one is set, or a file does not exist, startup fails with a config
+  error. Plain HTTP stays allowed.
 - **Startup warning:** when `server.host` is not loopback (`127.0.0.0/8`, `::1`, `localhost`) and HTTPS is not
   configured, `codetortoise serve` prints, to stderr and the log at WARNING:
   `Serving plain HTTP on <host>:<port> — logins (Perforce passwords) and source code cross the network unencrypted.
@@ -470,33 +470,41 @@ rest, HTTPS enforcement.
 ### 14.3 File tags on every visible item
 
 **Rule:** every item a viewer can see carries the Perforce depot paths it depends on, as `files: list[str] | None`
-(sorted, unique). `None` means unknown; stage 2 treats unknown as owner-only (fail closed). Tags are stored with the
-item and returned by the API unchanged; stage 1 filters nothing. "Depends on" means: any file whose contents produced
-the item's text, name or existence, including code given to the LLM as context.
+(sorted, unique). `None` means unknown; stage 2 treats unknown as owner-only (fail closed), and a tag built from any
+unknown part is unknown. `[]` means the item depends on no Perforce file (e.g. a function defined in a system header,
+outside the workspace). Tags are stored with the item and returned by the API unchanged; stage 1 filters nothing.
+"Depends on" means: any file whose contents produced the item's text, name or existence, including code and findings
+given to the LLM.
 
-| Item | `files` |
+| Item | Tag |
 |---|---|
-| Board node | its own `path`; a node without a path (no visible definition, e.g. `hal_read`) gets the files of the nodes that call or read it, since its name comes from their code |
-| Board edge | both ends' files |
-| Impact (annotation) | `path`, plus the files of `node` and of `cause` |
-| Flow | files of every step (`path`, `lands`, `fx_at`); template `title`/`what`/`effect`/`check` use these |
-| Flow LLM text (`what`, `title`) | `what_files`: every file whose code was in the prompt (path nodes and any context snippets) when `what_source == "llm"`, else equal to `files` |
-| Finding | its nodes' files plus evidence paths (`files`); LLM explanation, verify steps and hypotheses: `explain_files`, the prompt's files (finding nodes plus neighbours), `None` when not LLM-written |
-| Board layer name | files of the board's nodes in that layer (names come from directory names; stage 2 falls back to `L<n>` when hidden) |
-| About: tree file | itself |
-| About: changelist (number, user, description) | that changelist's files |
-| About: why line | its finding's `files` |
-| About: intent | `intent_files`: the LLM prompt's files when `intent_source == "llm"`, else all changed files |
-| About: drift line | that file |
-
-**Derived, not stored — `comment_scope(review, anchor)`:** line → the anchored file; function → the function's node
-files; finding → the finding's `files`; flow → the flow's `files`; chapter (layer) → that layer's files; review → all
-files of the review. The review's title and CL list use the review scope (all files of its changelists). `/files`
-diffs and `/source` text are addressed by path and need no tag.
-
-**Boards and findings stored before this change:** on load (the `/board` and `/findings` re-validation), structural
-tags (nodes, edges, impacts, flows, tree, changelists, drift, why, layer names) are derived exactly as above from the
-stored board; LLM-written text gets `None`; template text is derived like new boards.
+| Board node | `files`: its own `path`; a node without a path (no visible definition, e.g. `hal_read`) gets the files of the board nodes that call or read it, since its name comes from their code; unknown if none is on the board |
+| Board edge | `files`: both ends' files |
+| Impact (annotation) | `files`: `path`, plus the files of `node` and of `cause` |
+| Flow | `files`: files of every step (`path`, `lands`, `fx_at`); template `title`/`what`/`effect`/`check` use these |
+| Flow LLM text (`what`, `title`) | `what_files`: equal to `files` for template text; for LLM text, the files of the prompt (its steps' code and facts, and its findings' files) plus the flow's own `files`, since the text stands in for the flow's |
+| Finding | `files`: its nodes' files plus the files its evidence points at; `explain_files` (LLM explanation, verify steps, hypotheses): the finding's `files` plus its nodes' and their graph neighbours' files, `None` when not LLM-written |
+| Board layer name | `files`: files of the board's nodes in that layer (names come from directory names; stage 2 falls back to `L<n>` when hidden) |
+| About: tree file | `files`: itself |
+| About: changelist (number, user, description) | `files`: the tree files in that changelist. Its file count moves from `files` to `file_count` (stored boards are migrated on load) |
+| About: why line | `files`: its finding's `files` |
+| About: intent | `intent_files`: for LLM text, the files of every chapter's nodes and findings and of the first 30 findings (the summary prompt's inputs); for template text, all changed files |
+| About: drift line | now `{text, files}` with `files` = that depot file (stored string lines are migrated on load) |
+
+Graph nodes behind findings and LLM prompts are not all on the board. Their files come from the impact graph: a node's
+own file looked up through Perforce (one batched lookup per review, each file asked once); `[]` outside the workspace;
+unknown when the lookup failed; a node without a file (e.g. a field) takes the files of the nodes that access it.
+
+**Derived, not stored — `comment_scope(board, findings, anchor_kind, anchor)`:** line → the anchored file (`path`, or
+`depot` for M1 anchors); function → the board node's `files` (unknown if not on the board); finding (anchored by kind
+and title) → its `files`, plus `explain_files` once explained; chapter (layer) → that layer's `files`; review →
+every tag on the board and on the findings (`review_files`). The review's title names only its CL numbers and needs no
+tag; the CL list's descriptions use each changelist's tag. `/files` diffs and `/source` text are addressed by path and
+need no tag.
+
+**Boards and findings stored before this change:** on load (`/board`), structural tags (nodes, edges, impacts, flows,
+tree, changelists, drift, layer names) are derived as above from the stored board; why lines take their findings' tags;
+LLM-written text gets `None`. Findings stored before this change keep `None` (their graph lookup is not repeated).
 
 ### 14.4 Remove unused endpoints
 
@@ -506,13 +514,17 @@ them. Two fewer surfaces to tag and secure.
 
 ### 14.5 Tests
 
-- pytest: startup warning shown for a non-loopback host over plain HTTP, not for `127.0.0.1` or with HTTPS configured;
-  one-sided TLS config is an error; cookie `Secure` only with HTTPS.
+- pytest: startup warning shown for a non-loopback host over plain HTTP (including `::` and host names), not for
+  `127.0.0.1` or with HTTPS configured; one-sided TLS config and a missing certificate or key file are config errors;
+  cookie `Secure` only with HTTPS.
 - pytest: every board item and finding on the fixture review has non-empty `files`; FL1's `files` are
   `app/main.c`, `service/logger.c`, `driver/uart.c`, `driver/uart.h` (depot paths); a pathless node gets its caller's
   file; LLM flow text whose prompt included a neighbour snippet lists the neighbour's file in `what_files`; finding
   `explain_files` include neighbours; `comment_scope` for each anchor kind; a stored old board gets structural tags and
-  `None` for LLM text; the two removed endpoints return 404.
+  `None` for LLM text; the two removed endpoints return 404. A review run with an LLM stores `what_files`,
+  `explain_files` and `intent_files`.
 - vitest: banner rule (http + non-loopback → shown; https, localhost, 127.0.0.1, [::1] → hidden).
+- e2e (phone, network host name): the banner and the phone board fit the screen together (tab bar visible, no
+  horizontal overflow).
 - e2e: no banner on the e2e server's loopback address; the same server opened as a non-loopback host name
   (Chromium `--host-resolver-rules="MAP ct-lan.test 127.0.0.1"`) shows it, on the login page and on a review.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_provenance.py -q`
Expected: `10 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `217 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/provenance.py docs/superpowers/specs/2026-10-01-review-board-design.md backend/tests/test_provenance.py
git commit -m "feat(comments): comment scope from the anchor, for stage-2 filtering"
```

---

## Spec Coverage

| Spec §14 | Where |
|---|---|
| 14.1 context and staging | no code; constraints in Global Constraints |
| 14.2 optional HTTPS, startup warning, banner | Tasks 1, 2 |
| 14.3 file tags: board and change summary | Task 4 |
| 14.3 file tags: findings, graph nodes | Task 5 |
| 14.3 file tags: LLM text | Task 6 |
| 14.3 comment scope; spec as built | Task 7 |
| 14.4 remove unused endpoints | Task 3 |
| 14.5 tests | every task |

## Finish

- [ ] Run everything: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q` (expected `217 passed`) and
  `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test` (expected `Tests  69 passed (69)`, `24 passed`).
- [ ] See the banner on a phone: serve with `server.host: 0.0.0.0` and open the LAN address; the amber strip shows on the
  login page and the board, and `codetortoise serve` prints the warning. With `tls_cert`/`tls_key` set, both disappear.
