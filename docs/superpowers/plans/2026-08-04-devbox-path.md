# Devbox Forester PATH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cargo's `forest` command and both Dune-built Forester output directories available through the Devbox shell's `PATH`.

**Architecture:** Keep the change in the existing `devbox.json` `init_hook`. After the hook sources `~/.zshrc`, prepend `$HOME/.cargo/bin`, the default Dune Forester directory, and the install Dune binary directory, while retaining the prior PATH after them.

**Tech Stack:** Devbox JSON configuration, POSIX shell `export PATH`, Dune build output directories.

## Global Constraints

- Modify `devbox.json` only for the implementation.
- Preserve the existing `init_hook` commands and unrelated uncommitted changes.
- Add `$HOME/.cargo/bin`, `$PWD/_build/default/forester/bin/forester`, and `$PWD/_build/install/default/bin` to `PATH`.
- Place the PATH export after `source ~/.zshrc`.
- Do not run `dune clean`, `dune build`, or modify generated build output.
- Do not commit changes unless the user explicitly requests a commit.

---

### Task 1: Extend the Devbox Init Hook

**Files:**
- Modify: `devbox.json:9-13`
- Test: shell-based JSON and hook-content verification commands

**Interfaces:**
- Consumes: the existing Devbox `shell.init_hook` array.
- Produces: a Devbox shell where `forest` resolves from Cargo and Forester resolves from either Dune output directory when those artifacts exist.

- [ ] **Step 1: Verify the current configuration before editing**

Run:

```bash
node -e 'const fs=require("fs"); const c=JSON.parse(fs.readFileSync("devbox.json", "utf8")); const h=c.shell.init_hook; if (!Array.isArray(h)) throw new Error("shell.init_hook must be an array"); console.log(h.join("\n"));'
```

Expected: the existing hook is printed, including `source ~/.zshrc`, and no JSON parse error occurs.

- [ ] **Step 2: Add the PATH export after `.zshrc` sourcing**

Update `devbox.json` so the `init_hook` ends with:

```json
"source ~/.zshrc",
"export PATH=\"$HOME/.cargo/bin:$PWD/_build/default/forester/bin/forester:$PWD/_build/install/default/bin:$PATH\""
```

Keep the existing welcome message and `DEVBOX_PROMPT_NAME` assignments unchanged.

- [ ] **Step 3: Verify JSON validity and exact hook ordering**

Run:

```bash
node -e 'const fs=require("fs"); const c=JSON.parse(fs.readFileSync("devbox.json", "utf8")); const h=c.shell.init_hook; const source=h.indexOf("source ~/.zshrc"); const path=h.indexOf("export PATH=\"$HOME/.cargo/bin:$PWD/_build/default/forester/bin/forester:$PWD/_build/install/default/bin:$PATH\""); if (source < 0 || path !== source + 1) process.exit(1); console.log("devbox init_hook PATH configuration: ok");'
```

Expected:

```text
devbox init_hook PATH configuration: ok
```

- [ ] **Step 4: Inspect the focused diff**

Run:

```bash
git diff --check -- devbox.json
git diff -- devbox.json
```

Expected: no whitespace errors, and the focused diff adds only the PATH export required by this task. Existing unrelated changes in the worktree must remain untouched.
