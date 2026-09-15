# Changelog

## v2.0.0-dev — Stage 2 (in progress)

**v2 replaces Claude Desktop as the entry point. The app drives Claude Code as
a subprocess, so it runs on the existing subscription with no API billing.**

Stage 1 (foundation, prompts, retrieval eval, bootstrap) and Stage 2 items 1-5,
7, 8 and 9 are complete and verified live. Item 6 is done except its
scheduler, which is the only feature left in the build order.

### The commit log is the memory (2026-09-15, evening)

- **Repo is the landing view; the Inbox tab is gone.** A commit's body is
  the record of where a piece of work was left, so opening a project is
  reading where you stopped. The newest commit opens expanded under its
  module, any other on click; a bodiless one says so. The rail is
  Terminal · Repo · Stats · Settings. The Inbox digest built this morning
  — and the Brief before it — were summaries of what the commits already
  said; both are deleted, with the sittings file and the presence
  heartbeat. What *arrives* moved to Settings' new **Maintenance**
  section: nightshift's last run as one sentence (`GET /v2/nightshift`),
  red when broken, and the proposals with accept/reject as before. A job
  gone stale becomes a proposal there, which closes the loop the digest's
  "owed a decision" line used to close.
- **Every commit says where it leaves things.** A rule in
  `prompts/system.md`'s Git section: a body, whose last paragraph says
  where this leaves things and what comes next. The push refuses a
  bodiless commit dated after 2026-09-17 — the rule cannot reach back —
  alongside the attribution check, and nothing is pushed on a refusal.
- **Attribution by evidence.** `store.session_for_commit(subject)` finds
  the session whose transcript ran the commit (tool calls are indexed with
  their arguments); that session is the author, whatever tab was open.
  A session Noctis did not launch is filed by its directory — inside a dev
  job's project, or a subdirectory, it is Faber's — both at indexing and
  when an already-filed General session is read back. Only unclaimed
  commits fall to ownership, then to the clock. A Noctua tab open in the
  vault all afternoon had been credited with thirty of Faber's commits.
- **Record is the union.** A project's Record fold shows vault commits
  touching its notes paths *and* vault commits made from inside the
  project (the log, the lessons, the job context), in git's order, each
  marked `path` or `session` — and carries the same figures and push
  block as the project, pointed at the vault.
- `_git`'s `strip()` was eating a trailing `\x1f` — Python counts the unit
  separator as whitespace — which lost the newest bodiless commit from
  every log read; the record parser pads instead.

### Nightshift on record; the regression suite scoped and run from Settings (2026-09-15)

- **Every nightshift run is recorded**, and the Inbox digest reads it.
  `nightshift/report.py` writes one entry per run to
  `backend/data/nightshift.json` — when, what staged, what failed and why —
  and `summary()` names the outcome (`staged`, `quiet`, `partial`,
  `broken`) with how many nights in a row have ended the same way. The
  digest's first card says "Nightshift ran at 03:00 — 2 proposals staged",
  or "Nightshift failed at 03:00 — No such file or directory: 'claude' (41
  nights running)", and a broken night is a *next*. When every item fails
  with one error the runner exits non-zero and says so, instead of "quiet
  night". Six weeks of silence are what this is for.
- **The regression suite is a module** (`prompts/regression.py`), and the
  card runs it. Scope follows composition: an edit to an overlay runs that
  mode's cases, an edit to `system.md` runs all of them, `rule:<name>` runs
  every case guarding one rule — a structural mapping, not a judgement.
  Every case in `regression.jsonl` now carries its `rule` (eleven rules
  across thirteen cases). A failing case reruns once before it counts: one
  failure is a flake, two is a signal, and a per-case retry cannot hide a
  real regression the way the old suite-wide 11-of-12 bar could. Cases run
  three at a time. Each result is recorded per case with the hash of the
  composed prompt it ran against; a result the prompt has moved past shows
  as **stale**, so "the suite is green" is a state that accumulates over
  small runs rather than a thirteen-session ceremony. `POST
  /v2/regression/run {scope}` starts a run in a thread (one at a time;
  409 otherwise), `GET /v2/regression/status` is polled by the card, and
  `GET /v2/regression` returns every case with its last result — reading
  never runs anything. `run_regression.py` is the same module from the
  command line, with `--scope`.

### Settings' Save tells the truth, and nightshift finally finds `claude` (2026-09-15)

- **Save is the write.** `PUT /v2/prompts/{id}` writes the file in the
  vault and returns its path and size; that is the whole save, because
  `system.md` is what `~/.claude/CLAUDE.md` links to and an overlay is
  composed into the argv at the next spawn. It used to go on to "re-render"
  per-mode config dirs the 2026-09-12 cutover had removed, answering
  "config dir missing" five times per save, and the card said "re-renders
  every mode" for three days after that stopped being true. The card now
  says what happens: saved to the vault, uncommitted — commit it from Repo;
  the next session reads it, running ones do not. The button is the
  signature. Verified by round-trip: the file's mtime advances, byte for
  byte what was sent.
- **The system prompt lost its banner.** `compose()` prepended
  `<!-- GENERATED … Rendered <timestamp> -->` to every prompt sent in
  `--append-system-prompt` — describing a file that no longer existed, and
  putting a fresh timestamp at the head of every session's system prompt,
  the one place a cacheable prefix must not change. `render()` and the
  config-dir path in the regression runner went with it.
- **Nightshift has run nightly at 03:00 since 2026-08-05 — and failed every
  night.** `bootstrap.sh` installs its launchd plist; launchd's PATH has no
  Homebrew bin, so every advance step died with
  `No such file or directory: 'claude'` and the log said "quiet night". 47
  failures over 41 nights; only flagged-job items (no model needed) ever
  staged; not one lessons distillation ran. `scripts/nightshift_run.sh`
  exports its PATH now. The morning's "nothing runs on a schedule" in the
  docs and spec was wrong and is corrected.
- **`bootstrap.sh` step 3 would have undone the cutover.** It still
  symlinked `~/.claude/CLAUDE.md` to `modes/dev/dev.md`; it points at
  `prompts/system.md` now, and `bootstrap/README.md` describes the five
  steps the script actually runs rather than the seven it ran in August.

### A signature colour, and glass through the whole window (2026-09-15)

- **The signature.** One hue the interface's own readings are drawn in —
  a wine-rose (`--color-sig`, `#9c3f53`) in six steps from `#2a0b12` to
  `#de778a` — so a reading is never mistaken for a character's colour: the
  usage bars and their percentages (brightening as a window fills, in place
  of the green-amber-red traffic light), the activity ramp (was Faber red,
  which made a day's count read as a Faber thing), the token bar's four
  shares (were greys, which is what made them hard to tell apart), and the
  status bar's meters and context figure (were green and amber). The
  characters keep their accents; `--color-good` stays for diffs and pushed
  commits, which are outcomes rather than readings.
- **Glass through the whole window.** The body paints the ground once
  across the window and nothing else paints it: the rail, the title strip
  and the status bar had painted it a second time, and two coats at 0.62
  are 0.86 — the chrome read as a dark frame round a clear pane. The
  ground is heavier (`0.42 → 0.62`) so the words on it read over a bright
  desktop.
- **Settings loses its Schedule card.** It was the switchboard for the
  scheduler, and the scheduler was closed this morning; a section whose
  content is "nothing lives here" is not a section. Settings is Prompts and
  the Regression suite. Running the suite from the app is still to come.
- **Pools on Stats only.** They were on the Repo modules too and looked
  wrong against the folds and the push row; the Repo view will get its own
  treatment.

### One glass, one set of corners (2026-09-15)

- **Corners on a scale.** Nine radii between 1px and 6px, chosen per
  element, become three tokens: `rounded-card` (8px) on anything that is a
  panel of content, `rounded-sheet` (12px) on the overlays, `rounded-control`
  (6px) on anything you press or type into. Marks — cells, dots, bars —
  keep their tiny radii, because at 7px wide a 6px corner is a circle.
- **The terminals stay a slab.** They were made cards for an afternoon and
  it looked wrong — a terminal is the work surface, not a panel on it. Back
  to the rules between panes and the accent strip on the focused one.
- **Every view centres itself** when shorter than the window, not just Repo
  and Stats; Inbox and Settings used to start at the top.
- **Sheets are opaque.** The launcher, palette and reader sat on `surface`
  and the page's own text read through them — the one place glass works
  against you. A `--color-sheet` token, `#181818`: a sheet floats over the
  page, not the desktop, so there is no glass to lose.
- **The focus ring is one pixel** of the accent at 70%, not two solid: ⌘K
  and ⌘T focus their field from a keystroke, which counts as focus-visible,
  and the old ring read as an error state around the search box.
- **The pools are ours, and cheap.** `Pools.tsx` is border-beam's
  pulse-outside rebuilt (MIT): thirteen pools at even intervals — five
  along the top, four along the bottom, two up each side — at the library's
  own size, so each stays a distinct pool with dark edge between it and the
  next (a wider cut where the pools merged into one band was refused). Every
  pool is unique: its periods, drift, swing and phase come from its own
  seed. And the frame is cheap: the library paints all the pools into one
  stacked-gradient background and moves them by rewriting custom
  properties, re-rasterising three full-card gradients thirty times a
  second and blurring two — on a 1240px card that stalled the interface.
  Each pool is now its own element, painted once, moved by `transform` and
  `opacity` alone, its softness in the gradient rather than a filter. Stats
  measures at a locked 16.7ms per frame with zero frames over 33ms. The
  package and the halo are gone; silver, or Faber's red for a build.

### Border beam on the cards (2026-09-15)

- **Stats cards and Repo modules carry a border beam** — the `border-beam`
  package (MIT, React-only, no dependencies) at libraries.dev/beam's
  "pulse outside · mono" setting: soft light pooling at points around the
  edge and blooming outward, breathing, never travelling. Silver on every
  card; **a repository that is a dev job's project takes the `sunset`
  palette held still** — the library's four palettes have no Faber red and
  warm orange-red is the nearest. Two hand-written versions preceded it in
  the same afternoon, a pulse and then a rotating arc, both built from the
  reference's screenshot and hero examples rather than the playground at
  those settings; both read as something else. The motion lives in the
  library's JavaScript, not in a stylesheet that can be copied, which is why
  the package rather than a port. Declared in the spec's Design Brief.
- **The pulse encompasses the card.** The library pools light at seven
  points and leaves the edges between them dark, so under it sits a `.halo`:
  one even glow the card's own shape, a few pixels outside its edge,
  breathing on the same 2.3s cycle, faint by design — the floor the pools
  rise from. The pools stay mono everywhere; the halo carries the colour,
  silver or Faber's red for a build (the library's `sunset` spilt yellow and
  is dropped).
- **Glass, heavier.** Surface `0.55 → 0.72`, elevated `0.70 → 0.84`: a
  card's contents read differently over a light desktop and a dark one, and
  the Activity grid's empty cells could vanish. The empty cell is now a
  fixed step above the card (`rgba(255,255,255,.06)`) rather than an opaque
  near-black. The vibrancy is pinned to its active appearance
  (`windowEffects.state: "active"`), so the window no longer washes to grey
  when it is not in front — that was macOS's inactive material, not a bug in
  the shell. Takes effect on the next launch.
- **Lifetime tokens as one stacked bar.** The four kinds — input, output,
  cache read, cache write — as shares of one total on a single bar, greys
  darkest to lightest, with a dot-and-figure legend beneath, in place of
  four bars on four scales. Cache reads are three thousand times the input,
  so the small kinds are slivers with a 2px floor; the legend carries the
  numbers the bar cannot.

### The Inbox absorbs the Brief: a digest, computed, no scheduler (2026-09-15)

- **One tab for what arrives.** The Brief tab is gone and the Inbox moves to
  the top of the rail, opening with a **digest** — what happened across
  Noctis since you were last here and what is next — and then what is
  waiting on you. The digest's lines are counts turned into sentences:
  sessions run since, by character with their titles; each repository's
  commits since, commits not pushed, files uncommitted (the vault, then every
  dev job's project); proposals that arrived; jobs untouched fourteen days
  and owed a decision; the freshest open job per character. `GET /v2/digest`
  supplies the counts, `digestLines` composes the sentences and is tested to
  the string. No file, no scheduler, no model.
- **Why.** The brief was a vault file a `launchd` job was meant to rewrite
  each morning, with a model-written paragraph over the facts. The job was
  never built, so the card said "Thursday 10 September" for five days; and
  the paragraph was the one sentence in the app nothing could check — its
  prompt was twenty lines of warnings about the mistakes it made anyway. The
  facts it summarised already existed live elsewhere in the app.
- **"Since you were last here" is a sitting, not a clock.** The shell posts
  `POST /v2/digest/here` on open and once a minute while the window is
  focused and something was typed or clicked in the last two minutes; thirty
  minutes without one ends a sitting, and the digest reads from the previous
  sitting's end — so it holds still while you are here and moves on when you
  come back. First look: the last day.
- **Removed:** `brief/generate.py` and its prose prompt, `GET /v2/brief`,
  `POST /v2/brief/generate`, `PUT /v2/worklist`, the Worklist textarea, the
  vault's `brief/today.md` and `worklist.md`, and the scheduler from the
  build order — nothing left needs one. The MCP `worklist` tool stays: it
  reads each mode's `state.md` and never read the file.

### Stats: the list price covers every turn, and the page centres (2026-09-15)

- **$2,427 across 8,090 turns, not $102 across 120.** The list-price line
  was summed from the store's `list_cost_usd`, which only the retired `-p`
  engine ever filled — 120 turns carried a figure and every transcript-indexed
  turn since was written at zero. It is now priced from tokens, per model,
  by `orchestrator/pricing.py`, over the same transcripts the token counts
  are summed from, so cost and counts are one population. Rates were checked
  against the engine's own 120 figures: they reproduce to the cent at the
  1-hour cache-write rate (2× input) and miss by a third at the 5-minute one,
  which is how the TTL the CLI uses was settled. `priced_turns` now counts
  turns whose model the table knows; the line says `N of M turns` only when
  they differ. The recorder writes the same price into its rows at index
  time, so the two never disagree.
- **Centred like Repo.** The page sits in the middle of a window taller than
  it and scrolls from the top of one that is not. The figure groups its
  thousands like the total above it.

### The Repo tab: one module per repository (2026-09-15)

- **A repository is one box.** Name and branch on the lid, its terminals and
  path, where it stands and the push, then Uncommitted, Commits, Record and
  GitHub as folds inside the same border — the grouping is the box, not the
  reader's inference. Modules lay out by the terminals' rule: a row up to
  three, a grid after; with more than one on screen the commit lists start
  folded.
- **Ten commits show; the rest scroll.** Subjects wrap instead of truncating
  — a line you cannot finish reading is a line you did not read — and the
  fold headers say `9 of 20 not on GitHub` rather than a cut-off subject.
- **Notes is Record.** "Notes" was too vague; "Documentation" would collide
  with the repo's own `DOCUMENTATION.md`. The vault side of a project is the
  build's *record* — spec, briefs, migration log — which is what `dev.md`
  calls it.
- The universal prompt names the vault's **absolute path** and the
  folder-to-character mapping (`modes/dev` is Faber, and so on): a session
  in a project directory could not resolve a relative `second-brain/`, and
  one reading `modes/` found four folder names and three character names
  with nothing joining them.

### Sessions restore one at a time (2026-09-15)

The dev stack was killed twice for memory while restoring six tabs. Measured
rather than guessed: the stack itself is ~370 MB; each open tab is a `claude`
process of 270–310 MB plus every user-scope MCP server it inherits
(`railway` 31 MB, `headroom` 15 MB, `noctis` 4 MB), so six tabs are ~1.9 GB —
and on a reload all six booted in the same second. Spawns now queue with a
700 ms gap; attaching to a session that survived the reload is not queued,
because it costs nothing. Whether hosted sessions should inherit the
user-scope MCP servers at all (`--strict-mcp-config` would give them only
`noctis`) is a capability decision left open.

### What nothing called (2026-09-15)

A scan of the code, the docs and the assets for what nothing references,
after a week that replaced the orchestrator with a terminal. Removed, each
confirmed by a caller search and the suites:

- **Backend routes nothing calls:** `GET /v2/config`, `GET /v2/sessions/history`
  (the list), `GET /v2/sessions/history/by-engine/{id}`,
  `GET /v2/sessions/history/{id}/recap`, `GET /v2/sessions/statusline` (the
  single read), `GET /health/strip` and the `health` router — with the
  orchestrator-era `PermissionAsk`/`PermissionDecision` models, the recap
  constants, and the store methods only they used (`message_count`,
  `save_recap`).
- **Modules nothing imports:** `session_prompt.py` (v1's session-start
  callout extraction), `health_strip.py`; `vault_io.read_binary` /
  `write_binary` (Design Lodge previews); `triggers.compute_diffs_awaiting_review`
  (tests only).
- **Three copies of one section reader** → one: `nightshift.apply._section`
  now serves the inbox listing and the runner's rationale and confidence
  extraction; `panels._section` and the runner's two hand loops are gone.
- **Frontend exports nothing imports:** the effort cycle (`EFFORT_*`,
  `DEFAULT_EFFORT`, `Effort` — the per-turn chip went with the composer),
  `uniqueLabel`, `patchEntry`, `HistorySession`, `ConfigPayload`; the
  transcript's `error`/`silent`/`handoff` block kinds and their renderers,
  which the transcript reader cannot emit; the character strip's `working`
  state, which no caller passed since the stream went.
- **`bootstrap.sh` steps 6 and 7** — creating per-mode config directories and
  wiring hooks into them — which the script itself called obsolete: identity
  travels in the argv and hooks ride in `--settings`.
- **Retired art:** `assets/world/` (the pixel backdrop), the v1 sprite sheet,
  and Custos's and Echo's sprites; `public/icons.svg` (template social
  icons). `NOCTIS_SCRATCH_ROOT` from `.env.example`, which nothing read.
- Two test functions defined twice (the first copies never ran); unused
  imports across six files.
- **Docs:** DOCUMENTATION's two "— removed" placeholder sections deleted and
  the rest renumbered (every `§` cross-reference updated); STATUS.md rewritten
  to the current state, its 400 lines of v1 pass logs left to this file.

Suites: 298 backend + 67 frontend after, from 326 + 75 — the difference is
exactly the tests that covered removed code.

### Both halves of one piece of work, in one view (2026-09-15)

- **Notes under the project.** A build has two commit paths on purpose —
  code in the project repo, the record in the vault — and the second was
  invisible from the project's Repo group. Each dev job now names its notes
  folder (`notes_path` in the job context, `wiki/<Project>/` by default),
  and the Repo view shows the vault's commits and uncommitted files that
  touch that folder or the job folder as a **Notes** section under the
  project, with the same marks and its own push button (pushing the vault
  pushes the whole vault; the count says so).
- **`CLAUDE.md` is the contributor document**, and says so: it stays in the
  repo because Claude Code loads it from the working directory, and it and
  the repo's other docs must carry every decision a contributor needs —
  deploy target, push rule, no-attribution rule, stack — and nothing that is
  only the build's own reasoning. A `dev.md` proposal in the maintenance
  inbox makes this every project's rule.

### The plan moves to the vault; the README describes the rail (2026-09-15)

- **`SPEC.md`, `PTY-MIGRATION.md` and `PRODUCT.md` leave the repo** for the
  vault's `wiki/Noctis OS/`, beside `noctis-v2-SPEC.md`. They are the planning
  and build record — open questions, design briefs, a migration's decision
  log — and the public repo is for what runs: README, DOCUMENTATION,
  CHANGELOG, STATUS, SETUP. `CLAUDE.md` points at the new home. They stay
  in history (public since July); nothing was rewritten for this.
- **README rewritten around the rail.** One section per tab — Brief,
  Terminal, Repo, Stats, Inbox, Settings — saying what each does today, plus
  the keys. The architecture, the checkable claims and the blast radius stay.
- On GitHub is a green dot now, not a grey one.

### The push is a button, and it is yours (2026-09-15)

- **"claude" reached the public Contributors graph.** Four commits carried a
  `Co-Authored-By: Claude …` trailer — three from July already on GitHub,
  one from 09-12 carried by a push a session made at Shayne's word. Both
  histories rewritten locally with `scripts/strip_claude_trailers.py`
  (`filter-repo --message-callback`); the force-pushes are Shayne's.
- **A push button on the Repo view.** `POST /v2/repos/push` runs `git push`
  as the machine's git identity through its own credential helper — the
  person's hand, exactly what the "session never pushes" rule reserves.
  Before anything leaves: every outgoing message is read, and one
  attribution line stops the push (409, nothing sent); a branch whose origin
  has commits it does not (a rewritten history) needs `force`, which the
  view asks for as a second click and runs as `--force-with-lease`. The
  stand card's sentence now says the button is yours instead of naming a
  terminal command.
- **The prompt says it in words.** `prompts/system.md` gains a Git section:
  never push on any instruction — point to the Repo tab — and never add an
  attribution line. Hosted sessions already have `git push` denied by
  `permissions.json`; this covers every other one.

### Whose commit, and a history without its database (2026-09-14)

- **Each commit wears the character whose work it is.** No trailer in the
  message — the no-attribution rule stands. A repository that is a dev
  job's `project_path` is Faber's project, so every commit to it is
  Faber's, whichever terminal typed it — the first version marked commits
  from a build session launched into VS Code as General, because that
  session carries no mode signal and the indexer files it as General. For
  a repository no job owns (the vault), the mark is the session live in
  that directory at the time, else any session live at the moment (the
  vault is written from every mode's directory), most recently started
  winning; a commit outside every span, made by hand, gets none. The
  commits header carries a legend: red dot not on GitHub, grey on GitHub,
  face whose session.
- **`backend/data/` filtered out of the local history.** `git filter-repo
  --path backend/data --invert-paths` on the 210 unpushed commits: the
  root moved `49f3a0f` → `745b718`, `origin/main` is still an ancestor,
  nothing on GitHub changed, and a sweep of every commit found no API
  token, no `.env`, no bearer literal. Hashes cited in today's earlier
  changelog entries are the pre-filter ones; `.git/filter-repo/commit-map`
  has the mapping.
- The vault link "failing" was a browser profile not signed in to GitHub
  looking at a private repository; the public one opens.

### A group moves as one, links open, and the Repo view answers at once (2026-09-14)

- **A split drags as a module.** The bracket around a group's tabs is what
  you drag; its tabs are not draggable on their own, so a group cannot be
  pulled apart by accident. Dropping anything onto a grouped tab lands
  before the whole bracket. `onReorder` moves a block of ids in order.
- **Links open.** The webview does not honour `target="_blank"`, so the
  slug, pull-request and issue links did nothing. A Rust `open_url`
  command hands http(s) links to macOS's `open`; outside Tauri the page
  falls back to `window.open`.
- **The Repo view no longer waits on GitHub.** `/v2/repos` returns the local
  half at once (git answers in a tenth of a second) and carries the slug;
  the shell reads `/v2/repos/github?slug=` per repository afterwards, with
  "Asking GitHub…" in the card until it lands. That route runs its three
  `gh` calls at once and caches an answer for a minute; failures are not
  cached. Two repositories went from three seconds of "Loading…" to instant.
- The folded commits row shows the newest subject, so two columns that both
  read `20 · 20 not on GitHub` still say whose history each is. Terminals
  and the path sit on their own truncating rows so two columns keep the
  same rhythm.

### Split screen, and the views seen again (2026-09-14)

- **Terminals side by side, then in a grid.** Slots that share a group are
  shown together, each fitting its own cell, the focused one marked by a
  rule in the mode's accent along its top. Up to three sit in a row; from
  four the grid squares up — 2×2, then 3×2, then 3×3 for the nine ⌘-digits
  reach — rather than thinning into strips.
- **Tabs drag in the app now.** They always could in a browser; inside
  Tauri the window's native drag-and-drop handler took the HTML5 drag first,
  so a tab never moved. `dragDropEnabled: false` on the window hands it back. `⌘⇧-number` splits the showing
  terminal with that tab (or unsplits it); each tab also has a `⊞`/`⊟` on
  hover. The strip brackets a split's tabs together so it is visible from
  the tab bar which terminals share the screen. Joining moves the tab next
  to its group so the bracket is one run; a group left with one member is
  no group. The arrangement, groups included, survives a reload.
- **Repo view, more than one repository:** the groups sit side by side, and
  each column's commit list is folded to `Commits · 20 · 7 not on GitHub`
  until opened, so the page reads as repositories first. Alone, a
  repository still gets the full page with its commits open.
- **A first uncommitted path lost its first letter.** `_git` strips its
  output, so a leading ` M path` line lost its space and a column-based
  parse cut the path to `ath`. Parsed by status code now, with a test that
  puts a modified file first.
- **Inbox packages.** One card per item: the sender's sprite, the title,
  a tag in the mode's colour, then what it is and what accepting does, then
  a provenance band with the decision on the right — accept outlined in the
  mode's colour. The diff is a diff: removed lines red, added lines green,
  each on its own tinted ground, headers faint, no strikethrough.
- The General mark is the Noctis star (the `Logo` the rail wears), not the
  Vite favicon that had stood in for it.
- A terminal is disposed one macrotask late, not one frame: xterm's
  `Viewport` queues a zero-delay `syncScrollArea` it never cancels, and a
  frame fired before it with three terminals opening — the errors came
  back and the seeded three-terminal repro proved the timer is the wait.

### A session says what it is, starts where its work is, and wears its face (2026-09-14)

- **No session opens empty.** A fresh terminal used to sit at the CLI's bare
  prompt, which looks the same whether the methodology loaded or not, and the
  first thing typed into it was "what are you". `interactive.py` now gives a
  fresh session — not a resume, which has its own history — an opening
  prompt asking it to say which mode it is, what the session is for, and
  where it is. The launcher's hint says so instead of "opens empty".
- **Where a mode starts.** General starts at the vault, not in whichever repo
  Faber was last in. Faber starts in the *projects* directory (`PROJECTS_DIR`,
  else `~/Developer`, else the parent of the last project used): which project
  a build session is for is the session's to establish — a continuation names
  one, a new build has none yet — so defaulting to the last repo pre-decided it.
- **The launcher's `⌘1–5` said five for four modes.** The hint counts the
  choices it offers.
- **Sprites instead of dots.** The tab strip and the Repo view's terminal chips
  show the mode's character — Faber's, Noctua's, Vesper's pixel sprites from
  `assets/characters/`, the Noctis star for General — where a coloured square
  stood. One `ModeMark`, so a terminal is the same picture in both places.
- **Two `_renderer.value.dimensions` errors on every launch, gone.** Opening
  an xterm schedules frames it does not cancel on `dispose()`, and each reads
  the render service, which throws once disposed. StrictMode's mount / cleanup
  / mount disposed each terminal in the tick it was opened, so those frames
  ran against a corpse. A terminal is now disposed only after its first frame
  has landed; an earlier cleanup leaves the disposal to the mount path.
- The prompt file's header and `render.py`'s docstring still described a
  `CLAUDE_CONFIG_DIR` render that no longer exists; both now say what happens
  — `~/.claude/CLAUDE.md` is a symlink to `second-brain/prompts/system.md`,
  the overlay rides in the argv, and Settings → Prompts edits the vault file
  in place.
- Playwright added as a frontend devDependency: `dev.md` names the screenshot
  loop as the UI approval gate, and until now nothing could drive the page.

### Repo: the repository, seen from Noctis (2026-09-14)

A rail item for the repository the showing terminal is in. Local truth
first and always — branch, how far ahead of and behind GitHub, what is
dirty, the last twenty commits with the ones GitHub has not seen marked —
and beside it what GitHub says through `gh`: open pull requests with a
one-word check state, open issues. One sentence under the numbers says what
to do next, written for someone new to git. Read-only by construction: a
session never pushes, so the view asks for a push in words rather than
offering the button. Opened against the real repos: `noctis-os` 201 commits
ahead of a public remote, `second-brain` 17 ahead, no PRs, no issues. The
workflow those numbers argue for is SPEC open question 9.

Same day, grouped: the view follows the arrangement rather than the one
terminal that is showing. `GET /v2/repos` takes every open terminal's
directory and groups them by repository root, so two Faber sessions on one
project are one group naming both terminals the way the tab strip does
(`faber · 1`, `faber · 3`) and a session on another project is a second
group below; the showing terminal's repository comes first, and a terminal
in no repository is listed at the end in words. A terminal that has `cd`'d
is grouped by where it is now, from the CLI's own status-line report.

### The inbox decides, and says what deciding does (2026-09-14)

Found live with two real proposals waiting: titles were slugs, summaries
were cut mid-word with markdown asterisks in them, an empty template sat in
the queue as "untitled", the rail badge was a literal `3` in the source, and
**accept archived the proposal without applying its diff** — the route's own
docstring argued that applying would be "maintenance's power through another
door", which inverted the design: the guarantee is that *maintenance* never
edits; the person accepting *is* the edit, and `audit.md` names this route as
where the deterministic apply happens.

- Each row now reads: the proposal's description (from Custos's index in
  `state.md`, which the listing never consulted), a one-line summary cut at
  a word, and **what accepting does** — "edits Faber's methodology in 2
  places and commits the vault; the next Faber session reads the new text"
  — derived from the diff by the backend, so it cannot be oversold.
  `read` opens the whole argument: rationale, the diff with removed and
  added lines told apart, evidence, confidence.
- **Accept applies** — all hunks or none (`nightshift/apply.py`), then the
  markers a proposal may carry (a lessons cursor, a job to close), archive,
  the index entry dropped, and a commit in the vault. A diff that no longer
  applies is a 409 with the reason and the proposal stays, visibly stale.
  Reject archives, drops the entry and commits too, so a no is on record.
- A decision that fails says why under its row. The first version swallowed
  the error, which is indistinguishable from a button that does nothing.
- The badge is the live count of proposals, re-read every 30s and the moment
  a decision is made here.

### Two lines and a row (2026-09-14)

- The tab strip is the rail's title band's height, from the same token, so
  the two bottom rules meet as one line across the window instead of
  stepping at the rail's edge.
- The bottom bar is one band with one rule. It had been two rows on the
  main side — a composer row and, under a second rule, the status row —
  with the rail-width cell spanning both, so the cell's top edge sat a row
  above the status row's, and the composer's row stayed as an empty band
  after the composer went with the orchestrator.
- The status-line script prints nothing back. Whatever it printed became
  the CLI's own status row inside the pane, and Noctis draws that bar
  itself from the same payload, under the terminal — a `noctis` row was
  the same information twice. The CLI keeps the row only for its own
  `/rc` indicator.

### The page keeps running while the window is hidden; tabs drag (2026-09-14)

- **Hidden is not suspended.** Closing the window hides it to the tray, and
  WebKit's default for a web view not in a window is to suspend it: the
  status bar stopped, the arrangement stopped being remembered, a terminal
  that ended was not indexed until the window came back. The window is
  now configured with `backgroundThrottling: disabled`
  (`WKInactiveSchedulingPolicy::None` underneath), so the shell runs the
  same hidden as shown. The sessions never stopped either way. Verified
  from the backend log with the window hidden for minutes: across 400
  consecutive page polls, never more than four CLI reports between two of
  them — no gap — where a hidden window had produced no polls at all.
- **A hidden pane spawns at a real size.** A slot that is not showing sits
  in a `display: none` box that measures nothing, so xterm stayed at its
  80×24 default and the session was born that wide — the CLI's boot
  banner, laid out once, came up truncated (*Opus 5 with high ef…*) in a
  pane four times as wide. Every terminal shares one pane, so a hidden
  one now borrows the size the showing one fitted to (120×36 before any
  has), and the observer corrects it the moment it shows. Hidden-ness is
  decided by the host element's own layout, not by FitAddon's proposal —
  inside `display: none` the addon proposes something tiny rather than
  nothing, and the first version of the check waited for a nothing that
  never came (found live: the hidden session at 5×20, the Rust floor).
  Proven by reading the PTY size off the tty: 38×169 for both panes after
  a reload, where the hidden one had been 5×20.
- **Tabs reorder by dragging**, the way a browser's do. Labels and ⌘1–9 are
  positional, so the order on screen is the order under the keys. The
  strip's empty space also drags the window — the title bar is an overlay
  with nothing in it, so this is the top edge you reach for.

### Sessions survive a reload (2026-09-14)

The PTY registry lives in the Rust process and outlives the web view, so a
reload of the page — ⌘R in development, recovery from a crashed page — now
**reattaches** to the sessions that were running rather than killing them
and `--resume`-ing copies that had forgotten their screens. VS Code's
terminal does the same across a window reload. Verified: two forced full
reloads, the same two `claude` processes and slot ids before and after,
not one spawn.

- Each session keeps a capped 2MB scrollback of what it printed; frames
  are numbered; `pty_attach` returns the scrollback, the number of the last
  frame in it, and whether the process has since exited. The shell holds
  frames while it replays, then writes only the ones numbered past the
  snapshot, then resizes so the CLI repaints if the pane changed size.
- Slots keep their ids across a reload (the remembered arrangement stores
  them). The mount-time reaper now kills only sessions no slot came back
  under.
- **Ending a session is an intent, not a side effect of unmounting.** The
  terminal effect's cleanup used to `pty_kill`, and React StrictMode runs
  mount → cleanup → mount on every page load — so the first attempt killed
  the session it had come back to attach to. ⌘W (`App.close`) and `r`
  (`restart`) kill; an unmount does not.
- **A session must not depend on being looked at.** The effect awaited
  `requestAnimationFrame` for its second fit, and WebKit suspends rAF while
  the window is occluded; a reload with Noctis behind another window parked
  every terminal on that line. Raced against a 120ms timeout now.
- A resume of nothing is recognised by the CLI's own *No conversation
  found* rather than by the clock alone — a boot slowed by MCP servers
  connecting, or parked while the window was hidden, outlived the
  five-second heuristic and reported "session ended" for a conversation
  that simply was not on disk.

### Debugging sweep, second pass (2026-09-14)

Three things found by running the whole loop for real — argv → PTY → turn →
exit → index → recap — rather than by reading:

- **Terminal sessions attribute to their own mode.** The telemetry hooks read
  `NOCTIS_MODE`, and a PTY child inherits the shell process's environment, so
  every terminal session was logging under whatever the shell happened to
  carry. `interactive-args` now returns an `env` map beside the argv and
  `pty_spawn` applies it. Proven end-to-end: a vesper probe's `Bash` call and
  `SESSION_END` landed in `vesper__noctis-os.log`, SessionEnd resolved
  `mode=vesper`.
- **Recaps no longer become history.** `one_shot` wrote a transcript per call,
  and the indexer — which reads `~/.claude/projects/` as the record — filed
  each as a `general` conversation titled "Summarise this conversation in ONE
  sentence…". Twenty-seven were on disk, twenty-six in history. Now
  `--no-session-persistence`; the existing ones are tombstoned.
- **Recaps no longer fire the repo's hooks.** The backend's cwd is this repo,
  whose `settings.local.json` bakes `--mode dev` into its hooks, so every
  recap's SessionEnd cleared dev's busy marker — sixteen times in a day. Now
  `--setting-sources user`.

- **The backend no longer sits at 640MB.** `lifetime_tokens` built every
  transcript's full conversation — every message body — on the way to four
  integers, and `_records` held each file twice (the text and its line
  list). Measured after one Stats visit: 644MB resident, and it stayed there.
  Now a usage-only scan (`scan_usage`, held equal to `read` by a test) over a
  line-streamed reader: 78MB after Stats, index, search, history, brief and
  five more cycles.
- **A session that never started can be restarted.** A pane whose backend
  was down, or whose spawn failed, printed its message and then swallowed
  every keystroke; the key handler was registered after the spawn. It is now
  registered first, both failures say `press r to try again`, and a backend
  that *refused* (HTTP 400, a directory that does not exist) is told apart
  from a backend that is not there.

- **History follows a session that is still running.** The indexer filed a
  transcript once and never looked at it again — and a session gets filed
  at whatever point it has reached, because Stats indexes on every visit
  and every terminal that ends indexes for all of them. This very session
  sat in history at 3,387 messages while its transcript held 4,219. Rows
  now record how many bytes of the transcript they were read from
  (`sessions.indexed_bytes`); a pass re-reads any file that has grown,
  replacing the row's messages and turns in place (the id survives, so links
  do), and a row filed as `general` before the status line named its mode
  takes the mode once known. Recorder-era rows are left alone. The first
  pass after upgrading re-reads every transcript row once — 95 in 0.8s.

- **The terminal ceiling says so.** Past nine terminals — the reach of ⌘1–9
  and the backend's concurrency cap — the launcher's Start and history's
  *resume in a terminal* opened a tenth slot no key could reach, under a bar
  reading 10 / 9. Both now show the reason in place of the button.
- **Resuming lifts a tombstone.** A conversation deleted from history, then
  resumed from a remembered slot, went on growing behind its tombstone and
  could never be filed again. Asking for a resumed session's argv is asking
  for it back.
- **A reload reaps its strays.** The PTY registry lives in the Rust process
  and a web-view reload does not touch it: the shell came back with fresh
  slot ids and every session from before kept running — 300MB each,
  counted live, eating the cap. On mount, anything registered that the
  mount did not bring back is killed and closed out of the live count.

- **A handoff that opens with a bullet no longer kills its session.** The
  carried summary rides as the CLI's positional prompt; one beginning with
  `-` was read by the option parser as `error: unknown option` and the
  session exited before the terminal painted. The prompt now sits behind
  `--`. Proven in a PTY: a two-bullet prompt, session alive, answered.
- **A status-line report with odd numbers is a live slot without a
  reading**, not a 500 every five seconds. And `history?limit=-1` no
  longer means every conversation ever (SQLite reads a negative LIMIT as
  none); the limit is clamped to 1–500.

And one lesson for the probes rather than the product: a long burst of input
ending in `\r` trips the CLI's paste detection, and Enter becomes a newline.
The e2e probe sends the text, waits, then sends Enter — which is what a person
does.

### Glass (2026-09-14)

The window is a macOS vibrancy material — `windowEffects: hudWindow`,
`transparent: true` — with the desktop blurred behind it, the way Finder's
sidebar and Spotlight are. Native, not a CSS imitation. The three ground
tokens are translucent to let it show: ground most open, surface and elevated
progressively more opaque so text stays readable whatever is behind the
window, and heavier than the effect looks like it needs, because text on a
blurred desktop wants a darker tint than the same text on black. The terminal
paints with `allowTransparency`, so it is not the one solid slab.

Requires `macOSPrivateApi: true` — a private Apple API, recorded in the spec
as a deliberate choice: it closes the App Store door and nothing else.

### The session is a terminal; the orchestrator is gone (2026-09-14)

**Steps 4–5 of `PTY-MIGRATION.md` §7, in three commits that each left the
tree working.**

`fb931f6` — what the backend actually depended on, moved out. The mode →
model table, the tool allowlist, the tracked permission policy, the MCP
config, the binary lookup and `one_shot` all lived in `driver.py` beside the
spawn; `engine.py` holds them now, and `transcript.py` holds
`blocks_from_messages`. `one_shot` — the one `-p` that remains, a script for
recap and the brief — moved to `--output-format json`, which is what let it
stop depending on the stream parser. Stats reads its lifetime figure from the
transcripts, taken on the diff's evidence rather than on schedule.

`092798b` — the shell, rewritten terminal-first rather than edited around
the transcript it used to host. Gone: the stream-built transcript, the
composer, the permission dialog, the pickers, the per-turn effort chip, the
Chat tab bar, the SSE reader and reducer, and the modules only they used.
Stays: ⌘K over history and the vault; a history row opens read-only with one
action, *resume in a terminal*; ⌘T opens the launcher; ⌘⇧H hands off, and
the carried summary arrives as the new session's first message. The
arrangement is remembered on every change and comes back resumed.

`7ba58e9` — the deletion. `driver`, `manager`, `parser`, `wire`, `events`,
the permission host and its MCP tool, the launch and permission routes,
`store.record`, and the tests that described them. `grep` found no importer
first. Caught while cutting: the first terminal version never passed the job
brief into the overlay — the never-called shape the 09-11 audit kept finding,
in its third guise; the wiring test watches the argv now.

Verified live: interactive-args carries the job section, the session list
reports three live terminals from their own status lines, Stats reads 2.5B
lifetime tokens back to 2026-05-11 — sessions Noctis never hosted. 287
backend tests, 60 frontend.

### Beside the recorder, and the recorder loses (2026-09-13)

Steps 2 and 3 of the migration wired in, plus three things the first real
click needed. **The status bar is live** — limits are polled on the same
four-second cadence as the live counter, so a terminal's `statusLine` reports
reach the bar instead of waiting for a reload. **Keys inside a terminal go to
the CLI** — the shell captures Shift+Tab, Escape and the arrows for itself,
and Claude Code's TUI uses all three; every ⌘-chord stays with the shell,
everything else passes through. **Several terminals, kept alive** — the view
stays mounted whichever rail item is showing, because the first version
unmounted on Stats and unmounting a terminal kills its session.

**The indexer files every transcript into history** (109 on first run) and
`/v2/sessions/stats` returns the lifetime figure from disk beside the
recorder's, with a per-session diff. Rows carry `source` so the diff only
tests what the recorder wrote — a row the indexer filed agrees with its own
transcript by construction, and the first version counted those.

**The honest diff: 1 of 16 agree, and the recorder is wrong.** Every
disagreement is the transcript being larger, 2–5×. On `dc88ea90`, checked
per field: 4 usage rows for 29 API calls, 6,486 output tokens recorded
against 13,252 on disk. Output cannot be inflated by cache re-reads. The
recorder writes one row per turn from `result.usage`, and that is not the
whole turn — it has undercounted since it was written, and the 09-08 fix
corrected the model's name, not its number. The transcript is the more
complete source; Stats switching to it is step 4, not yet done.

### The real CLI, hosted in a terminal (2026-09-13)

**Step 1 of the migration is in: a Terminal rail view running an interactive
`claude` in a pseudo-terminal, beside the existing transcript.** Noctis spawns `claude -p` — "print response and
exit" in the CLI's own help — once per turn, and most of the orchestrator
exists to rebuild the interactive loop on top of a scripting mode. Running the
CLI in a pseudo-terminal instead would delete that reconstruction.

It was rejected twice before, correctly, under a premise that no longer holds:
`Modes.md` called PTY capture "the original trap" when the interface launched
sessions into Terminal.app and read state back from files. v2 hosts its
sessions, and under hosting a PTY is not mirroring — it is how you run an
interactive process. The rejection was never re-derived when its foundation
was removed.

Every assumption tested against 2.1.263 rather than argued: a `/status`
injected into a PTY from outside renders and the process exits with no
orphans; `statusLine` delivers `five_hour`/`seven_day`, context window,
effort, cost, `session_id` and `transcript_path`; the CLI writes its own
transcripts **incrementally**, so a session SIGKILLed mid-generation keeps its
partial output; `--resume` appends without forking; `portable-pty` builds on
this toolchain at 773 KB with 20 dependencies. Termic already ships this exact
architecture — xterm.js + WebGL2 in Tauri with the PTY in Rust.

**Stats gets one raw lifetime token count.** The CLI's background calls are
absent from the JSONL, which is 146,327 tokens against 82,174,586 — 0.178%.
`aux_input_tokens`/`aux_output_tokens` go with the migration.

**What shipped:** `pty.rs` (PTY host: spawn, write, resize, kill, 16ms output
frames, base64 across the IPC), `interactive.py` (the argv — deliberately not
`build_command` with a flag), `Terminal.tsx` (xterm.js themed from
`tokens.css`, WebGL2 with a DOM fallback), `scripts/statusline.sh` +
`/v2/sessions/statusline` (the status bar's second source, which survives a
reload where the stream never did), and `orchestrator/jsonl.py` (history read
from the CLI's own transcripts).

**Nothing was deleted.** Chat still runs on the orchestrator. Switching the
default and removing the orchestrator are gated on the two paths agreeing over
real use — the 09-12 cutover removed `launch_config/` while a guard still
required it and broke every spawn.

Review: `PTY-MIGRATION.md`. Decision record: `SPEC.md` Open questions 7.
Reference: `DOCUMENTATION.md` §22.

### One command to run Noctis, and it opens the app (2026-09-13)

**`make app` is now `make dev`.** The naming had it backwards: the command with
the obvious name opened a browser tab, and the app was the thing you had to
know to ask for. You develop in the window you use, so a bug found while
working is a bug found in the real surface.

| before | after | |
|---|---|---|
| `make app` | **`make dev`** | Tauri window, supervised backend, `[tsc]` stream |
| `make dev` | `make browser` | browser tab at `:5180`, `uvicorn --reload`, no Rust build |
| `make backend` | `make reload` | kills uvicorn; the supervisor brings it back on current code |

`make browser` stays for backend-only work, where a Rust build is not worth
paying for. Product capabilities are identical across the two — everything
else is backend or frontend code.

`make reload` replaces `make backend`, which started a *second* uvicorn beside
the supervised one and clashed on the port. Killing it instead means a
deliberate restart and a crash take the same path, which is what crash-only
design is for rather than a special case bolted beside it.

**Fixed in the same pass, all found by sweeping rather than assumed:**

- **`desktop/NoctisOS.app` was broken.** Its launcher still ran `make app` — a
  target that no longer existed — so every double-click would have failed into
  `backend/runtime/desktop.log`, which nobody reads.
- **`test_the_supervised_backend_does_not_reload` had stopped running.** It
  sliced the Makefile at `\napp:` and threw `ValueError: substring not found`,
  so the "supervisor and reloader are alternatives, not layers" invariant was
  unchecked. It reads the `dev:` target now.
- **`supervise.py` pointed the wrong way twice** — its docstring and its
  already-answering error both told you to use `make dev` to get the reloader,
  which is now the opposite of what `make dev` is.
- **`DOCUMENTATION.md`'s troubleshooting table** still prescribed `make backend`
  for an absent backend.
- **`desktop/README.md`** described the pywebview shell deleted on 2026-09-12.
  Rewritten: the bundle is a double-click wrapper around `make dev`, plus the
  two lessons from that shell which still hold — cleanup needs process groups,
  and you verify by actually closing the window.

`CHANGELOG.md` and `STATUS.md` entries dated before today keep saying
`make app`; they are records of what the commands were at the time.

### The v1 cutover (2026-09-12)

v1 is gone. Removed: `World.tsx`, `ProfileOverlay.tsx`, `DesignLodge.tsx`,
`modes.ts`, `api.ts`, v1's `index.css` and `App.tsx`; the `mode`, `session`,
`nightshift` and `design_lodge` routers; `launch_surfaces.py`; every mode
config directory. The v2 shell calls only `/v2/*`, and nothing in it imported
from `src/` root, so the two halves came apart cleanly.

**Item 9, maintenance migration — closed.** Settings and Nightshift collapsed
into root-level `maintenance/` in September, but only their *methodology*
moved; two `MOVED.md` markers deferred the state because v1's pipeline still
read the old paths. With v1 gone the state followed: `state.md`, `lessons.md`,
`jobs/`, `inbox/` and `archive/` are now under `maintenance/`, the two state
files merged without key collisions beyond `mode` and `last_touched`, and the
two lessons files merged carrying nightshift's own security note — unattended
runs write with no human in the loop at write time, which the settings note
did not cover.

**The paths are named once.** There were eleven literals across six files, and
the mode→directory mapping had been restated three times and disagreed twice.
`jobs.py` owns them now, and `jobs_dir()` handles maintenance sitting outside
`modes/` rather than each caller assembling `modes/{mode}/...` and being wrong
for one of them.

**Item 8, tiered loading policy — removed rather than defined.** It appeared
in the build-order table and nowhere else: no description, no acceptance
condition, no trace in the vault. Its only defensible reading is what enters a
session's context at entry versus what it fetches on demand, and the system
already does that — capped job brief, overlay-as-pointer, opt-in retrieval.
The policy existed and was undocumented, not unbuilt. Written up in
DOCUMENTATION.md §4.

**api_error_status** is parsed, independently of `is_error`: a turn that died
on a provider 429 was reported as a plain empty turn, which sends you looking
in the harness for a fault that happened upstream.

**The v2 checkpoint is closed, passed.** Recorded four days late because until
09-11 the answer was contaminated — Faber could not run Bash, Edit or Write,
so any fallback to Desktop was forced rather than chosen.

### The harness itself (2026-09-11/12)

Not a numbered item — infrastructure debt that had been capping every one of
them. One cause, five symptoms, found by asking why Claude behaved worse
inside Noctis than outside it.

- **Sessions run against the real `~/.claude`.** `CLAUDE_CONFIG_DIR` pointed
  each mode at a private config root, and a config root is not a settings
  file: it is where plugins, skills, subagents, slash commands, MCP servers,
  accumulated permissions and memory all live. Redirecting it replaced the
  whole surface with an empty one, so Faber was reading a methodology naming
  Impeccable, the code-review plugin, a Critic subagent, Playwright,
  shadcn/Magic MCP and CodeRabbit — none of which it could reach. Neither
  launcher redirects now; a mode's methodology travels in the argv via
  `--append-system-prompt`, which also retires the only real argument for the
  split dirs (two sessions racing on a rewritten file) and turns off
  system-prompt snapshotting, so an edited methodology reaches a resumed
  session.
- **`~/.claude/CLAUDE.md` points at `prompts/system.md`, not `dev.md`.** The
  old symlink made the machine itself Faber. Harmless while every surface
  redirected away from it; a live leak into every mode the moment they
  stopped. The config root is infrastructure, never an identity.
- **Every mode gets the same tools.** `--disallowedTools` is gone. Capability
  was the wrong axis to vary on: a mode handed work it cannot perform ends
  its turn with nothing done and no way to say so. `git push` stays denied for
  all modes. Maintenance's propose-never-apply now rests on its methodology
  and the permission chip rather than a cage that also stopped it reading a
  repo it was asked to audit — a deliberate trade, recorded as one.
- **Permission requests are answered.** `--permission-prompts` took its `host`
  default with no host attached, so every request died unanswered and the
  chip's labels were fiction. The Noctis MCP server is the prompt tool now.
  Wiring it surfaced that the server had never been attached to any spawn
  since it was built — `vault_search` existed and nothing could call it.
- **Refusals and silence are events.** `permission_denials`, `terminal_reason`
  and `num_turns` had been sent on every result event and read by nothing. A
  turn ending with tool calls and no text renders as *"turn ended with no
  reply"*; one refused its tools renders as *"turn ended blocked"* with the
  refusals named. This is why `system.md`'s "never end a turn without
  user-visible text" kept failing: the rule was not ignored, it was
  unsatisfiable.
- **The composer chip sets effort, not permission.** `low`/`medium`/`high`/
  `xhigh`, default high. `dev.md` had specified effort routing since it was
  written while no code passed `--effort`.
- **Vault subagents are registered.** The Critic, and Noctua's and Vesper's
  rosters, reach sessions via `--agents` for the first time.
- **The vault's absolute path is stated in the prompt.** `system.md` gives a
  relative `second-brain/`, which resolves against the project; a live session
  reported the vault unreadable while reading it through MCP.
- **Capability contract.** `backend/capabilities.py` — each mode declares what
  its methodology assumes, the harness reports what it has, `make doctor`
  prints the gap. `--migrate` emits a harness-migration brief covering
  everything that would not port, as intent rather than settings.
- **One mode→path mapping.** Three copies existed across `jobs.py`,
  `orchestrator/modes.py` and `mcp/server.py`, and two disagreed about
  maintenance. `jobs.py` owns both `jobs_dir()` and `methodology_path()`, which
  genuinely differ for maintenance and now say so.
- **`make test` covers the frontend**, and `make doctor` / `make backend`
  exist. `tsc --noEmit -p tsconfig.json` checks zero files against this repo's
  solution-style tsconfig and exits 0 — it reported a clean typecheck on a
  broken tree.

### Session orchestrator
- `orchestrator/` drives `claude -p --output-format stream-json --verbose` and
  normalizes the CLI's events into a stable union the frontend renders. Two
  concurrent sessions, queued rather than refused — the cap is a budget on the
  5h window, not a resource limit.
- Per-mode tool policy is enforced at spawn (`--disallowedTools`), not by
  instruction: maintenance's propose-never-apply failed a plainly-worded
  request in the regression suite, so it has a cage as well as a rule.
- `bypassPermissions` is excluded from the permission cycle and rejected over
  the wire — a guard that exists only in the client is not a guard.

### Noctis MCP server
- Dependency-free stdio server exposing `vault_search`, `history_search`,
  `job_context`, `worklist`, `propose`, plus prompts and resources. The
  portable half of the system: the body is Claude-Code-shaped, the brain is not.

### Shell
- Tauri v2 + React. Global Opt+Space summon, tray, launch-at-login,
  close-hides-not-quits.
- Chat with block-structured transcripts, mode entry (⌘T), handoff to another
  mode (⌘⇧H), cross-mode search (⌘K), stop (esc).
- Handoff opens a *new* session rather than switching a live one's mode: mode
  is a config dir, a model and a tool policy, and a running `claude -p` can
  change none of them mid-flight.
- Conversations survive a restart. Stats, Brief, Inbox and Settings read real
  data; where data does not exist yet the page says so and names the file it
  is waiting for.

### Panels — brief, worklist, inbox
- **Morning brief**, two halves deliberately separated: facts computed in
  Python (which jobs are open, how old, what is waiting) and prose written
  over them. Counted, not estimated, so nothing rounds 45 days to "about a
  month" or invents a job that closed in July.
- **The worklist is hand-kept, not generated** — a generated worklist is the
  job list again under a second name, and the two would disagree the moment
  one drifted. Editable in place, saved on idle, through a route that writes
  one fixed path: writing into the vault is only safe from a route that
  cannot be told where to write.
- **Inbox** parses proposal sections properly. It had been taking the body's
  first line as the summary — the markdown header — so every row read
  `## Rationale` while the sentence explaining the proposal sat unread below.
- The scheduler that would fire these does not exist yet, so Settings names
  what it *will* run rather than showing dead toggles.

### Bugs worth recording (all found by running it, not by tests)
- **PATH.** launchd starts processes with `/usr/bin:/bin:/usr/sbin:/sbin` — no
  Homebrew — so a scheduled backend would never have found `claude` while
  working perfectly from a terminal. The engine is now resolved explicitly.
- **Tauri origin.** The packaged app serves from `tauri://localhost`, not the
  dev server's port, so the built app could not have reached its own backend.
- **Model attribution.** `modelUsage` is keyed by model and its first key was
  the CLI's *background* tier, while the token counts beside it came from the
  primary — the name and the numbers described different models. Fixing it
  exposed a larger bug underneath: the background tier's tokens were counted
  nowhere at all. On a measured turn that was 899 of 901 input tokens.
- **sqlite across threads.** FastAPI runs sync routes on a threadpool, so a
  store opened at import was never on the thread that later read it. Every
  stats request would have raised.
- **A row per turn.** `engine_session_id` is UNIQUE, so the second turn of any
  resumed session died on the constraint — and the same mistake scattered one
  conversation's transcript across many rows. A row is the conversation now.
- **No user messages.** `record()` folds engine *events*, and the person's own
  prompt is not one, so every stored transcript was answers with no questions.
- **Permissions never reached a session.** `CLAUDE_CONFIG_DIR` redirects where
  user settings are read from, so `~/.claude/settings.json` — and every rule
  ever accumulated in it — is invisible to a spawned session. Every mode had
  been starting with an empty allowlist. Fixed with one tracked
  `permissions.json` passed via `--settings`.
- **MCP version echo.** The handshake returned whatever version the client
  asked for. Told `1999-01-01` it agreed — and a client told its requested
  version is supported will then use features that were never implemented.
  The spec's handshake is a negotiation, not an echo.
- **Fonts vendored and never loaded.** JetBrains Mono shipped in every build
  with its `@font-face` in v1's `index.css`, which stopped being imported at
  the v2 cutover. The guard written to catch that then missed Cascadia Code
  itself, deriving the family from the filename before stripping the
  extension — the test would have passed while the font went unloaded.
- **Absence rendered as an answer.** The activity grid drew "0 sessions in the
  last year" while its data was still loading; ⌘K rendered "No matches." for a
  query it never ran against an unreachable backend; and "Loading…" could
  outlive its request, because a restarting backend can accept a connection
  and never answer while `fetch` has no timeout of its own — so the failure
  state the UI already knew how to draw could not be entered.
- **A cwd of `~`.** `openSession` fell back to it when a stored transcript had
  none, and the handoff built `~/Developer/`. Both are real directories, so
  validation passed and the session simply started in the wrong place — which
  made filesystem search sweep the home folder and time out, reading as a
  broken tool rather than a bad working directory.

383 backend tests, 76 frontend, `tsc -b` clean.

## v1.5.2 — 2026-07-28

**Fix: frontend dev-server port collided with other projects on this machine; nightshift's distiller model was a hardcoded literal.**

- `frontend/vite.config.ts` pins the dev server to `:5180` with `strictPort: true`, instead of relying on Vite's `:5173` default — which collides with other local projects' dev servers on this machine. `backend/auth.py`'s `ALLOWED_ORIGIN` and `backend/tests/test_auth.py` updated to match.
- `backend/nightshift/runner.py`'s `DISTILLER_MODEL` is now overridable via a new `NIGHTSHIFT_DISTILLER_MODEL` env var (documented in `.env.example`), rather than a hardcoded literal — the fix the model-upgrade audit (Custos, 2026-07-23) flagged: a smaller/newer tier can now be adopted without a code change.
- `.gitignore` gains `backend/launch_config/nondev/{chrome,ide,tasks}/` — Claude Code's own runtime state (a native-host binary, a PID lock file, session-UUID folders), same category as the other generated `launch_config/nondev/` entries already ignored, previously untracked but not excluded.

## v1.5.1 — 2026-07-27

**Fix: backend reload was dropping in-flight requests, plus two apply-pipeline bugs found by Custos's own spec-completeness audit on Noctis OS itself.**

- `uvicorn --reload` watched `backend/runtime/` with no exclusion — the PostToolUse/Stop hooks write action-feed logs and busy markers into that directory on every tool call of every live session, so ordinary hook activity was restarting the backend mid-request. Surfaced live as "Load failed" in the desktop app's WKWebView when an Echo accept/reject click landed in a restart window (Chromium reports the identical failure as "Failed to fetch", which is why a same-machine browser-tab repro came back clean). Fixed with `--reload-exclude 'runtime/*'` on both `make dev` and the desktop app's uvicorn invocation.
- `vault_io.py` could only ever resolve paths inside `VAULT_PATH` — a diff proposal targeting `noctis-os/SPEC.md` (a sibling repo, not vault content) had nowhere to resolve to and raised a bare `FileNotFoundError`. Every prior accepted proposal only ever targeted a vault mode file (`modes/<name>/<name>.md`), so this was never exercised before. Fixed with a narrow, explicit `noctis-os/` project-root allowlist rather than widening vault_io's writable root generally.
- `backend/nightshift/apply.py`'s target-path regex (`\S+`) stopped at the first space, truncating the one proposal targeting a wiki page (`wiki/Noctis OS/Modes.md`, a real space in a real folder name) to `wiki/Noctis`. Fixed to capture the whole line.
- 4 new regression tests (project-root resolution + traversal guard, the space-in-path fix, a mechanical check that the reload-exclude flag can't silently disappear from either launch path again) — 151/151 backend tests passing.
- `SPEC.md` itself gained 6 fixes from the audit that found these bugs: a direct contradiction (`busy` documented as a `state.md` field when it's actually been a separate runtime marker since 2026-07-22), three missing-but-shipped mechanisms (the `--append-system-prompt` session-start channel, Echo's History section, Faber's new-build scratch-directory flow), one undocumented pair of 2026-07-24 telemetry fixes, and one stale self-contradiction in its own Open Questions list (nightshift's scheduler was already locked as launchd elsewhere in the same file).

## v1.5.0 — 2026-07-25

**Design Lodge** — a vault-native, browsable/editable catalog of design assets, built as a full Overhaul (Plan amendments through `SPEC.md`'s PRD/EDD/Design Brief, Build, Ship). Distinct from the existing (still-unbuilt) "library catalog" feature, which is vetted *code dependencies* fed by research verdicts — this one is design components/patterns/palettes, fed by Faber's own build and capture flow.

- Backend: `backend/routers/design_lodge.py` — CRUD for entries plus a quick-capture inbox queue, all behind the existing bearer-token + Origin auth. `vault_io.py` gains `list_dir` and the vault's first binary read/write helpers (`read_binary`/`write_binary`) for preview images.
- Storage: `second-brain/design-lodge/index.md` (lightweight index, same pattern as every mode's `state.md`) + `entries/<slug>.md` per entry, vault-level rather than per-project so every future Faber build reads the same shelf.
- Frontend: new "design lodge" tab inside Faber's profile-overlay card (`DesignLodge.tsx`) — category-filtered browse grid with image-first previews (fetched as authenticated blobs, never a token in a URL), expand-to-reveal code/reference/tags, inline add/edit form with image upload, and the quick-capture inbox. Faber's card gains the same fixed-height exception already granted to Echo (auto-height, wider, viewport-capped) since the default card was too small for this content.
- Seeded with 7 real entries pulled from this repo and Portfolio Platform (typography pairing, world/character palette, typewriter reveal, caret-expand disclosure row, the 3D project card's rest-state camera-fit math, its separate expand/dive animation curve, and the two-column repo-card hero) — not fabricated placeholders; two Portfolio Platform visuals are honestly labeled schematic, not live WebGL captures.
- `dev.md` (global Faber methodology, applied via Custos's staged-diff process, not edited directly by this build): the Overhaul mechanic gained an explicit four-stage breakdown (Plan amends only, Setup is treated as already-satisfied with feature scaffolding folding into Build, Build re-triggers 3.0 scoped to the change, Ship keeps the full nine-step gate with an integration-fit lens) — plus three new Design Lodge touchpoints (Plan: browse before gathering references; Build 3.0: check-first before shadcn/Magic MCP/fresh inference, save keepers back; Ship: consistency check) and an opportunistic, non-blocking inbox-processing pass at session-bootstrap.

## v1.0.0 — 2026-07-21

Full build order complete (mode folders, backend, frontend tracker, telemetry hooks, nightshift infra, dev job lifecycle), two ship-gate passes run, deployed locally per the locked EDD (single-user, single-machine — nothing to deploy). Everything below.

- Fix: `desktop/NoctisOS.app` failed to launch from Spotlight/Finder double-click (`FileNotFoundError: 'npm'`, confirmed live) — LaunchServices runs the app with a minimal PATH that excludes Homebrew, unlike a terminal-launched `make app`. Resolves npm's absolute path with Homebrew-path fallbacks and passes an augmented PATH to its subprocess (npm's own `env node` shebang needs it too). Icon switched to the faber-building expression (2026-07-21)

- Desktop: `desktop/NoctisOS.app` is a real double-clickable app now (thin wrapper around `desktop/app.py`, always runs live source, not a frozen build) with a proper bundled icon — closes the "real .app bundle" follow-up flagged when the pywebview wrapper first shipped. Added a Refresh command (native menu item + Cmd+R/Ctrl+R) since a code change to this always-live-source bundle only needs a reload, never a rebuild. `make open-app` alongside the existing `make app` (2026-07-21)

- Fix: the busy indicator (expression swap + new label-highlight) was dropping mid-session because `mark_session_end.py` was registered on Claude Code's `Stop` hook, which fires after every agent turn, not on real session termination. Moved to `SessionEnd`; `_merge_hook` now also purges a script from any other event bucket it's still registered under, so old settings.json files don't end up firing the hook on both events. Label now also stays accent-colored while a mode's session is running, independent of the profile overlay being open, using the same `busy` flag as the expression swap (2026-07-21)

- Closed two spec-completeness gaps found by a real audit against `SPEC.md`: nightshift's confidence flag was always staged as `null` (settings' distiller now writes a genuine high/low self-assessment into a fourth mandatory `## Confidence` proposal section; dev's mechanical flagged-job note always gets `high`, no judgment involved); and staleness-flagging only worked for dev despite learn/research/settings promising the same failure behavior (`staleness.py` generalized to `flag_stale_jobs(mode)`, wired into all four; Noctua/Vesper/Custos's cards never rendered job rows at all, so extracted a shared `JobList` component so a flagged job is actually visible, not just tracked server-side). 10 new/updated tests, 94 passing (2026-07-21)
- Fix: `busy` was never set anywhere in the backend for any mode (found live — launching Noctua's session didn't update its card). `POST /session/launch` now sets it true; the Stop hook (`mark_session_end.py`) clears it false on clean exit. Hooks now invoke the venv's own Python explicitly rather than bare `python3` (2026-07-21)
- Fix: world screen letterboxed instead of filling the window (third pass) — `.world` is now `100vw`/`100vh` with the backdrop stretched to fill exactly, instead of a fixed 1376×768 canvas; sprite sizing stays tied to the container so it can never drift from the background regardless of window shape (2026-07-21)
- Desktop app: backend now runs with `--reload` (was missing, only frontend hot-reloaded); placeholder Dock icon via AppKit (Faber's sprite, real art to follow); flagged jobs can now be un-flagged (`JobUpdate.flagged`, resume clears it) — found live when noctis-os's own job got flagged from this session's file-edit-not-launched-session workflow (2026-07-21)
- Native desktop window: `make app` (`desktop/app.py`) opens Noctis OS as a frameless pywebview window (not Tauri — researched alternatives, pywebview stays 100% Python with no new toolchain, chosen for this single-user local tool). Fixed a real subprocess-cleanup bug found by actually closing the window (`npm run dev`'s child process survived `.terminate()`) using process groups; verified live with a real Cmd+Q keystroke, zero leftover processes. Custom app icon needs a bundler pass (`py2app`/`PyInstaller`), a follow-up (2026-07-21)
- World screen: fixed 1376×768 canvas, not responsive (supersedes the earlier aspect-ratio/container-query scaling attempts — direct feedback that the large-window layout should be the only layout); label font switched from Press Start 2P to JetBrains Mono for legibility at small sizes, reverted an opaque-fill experiment back to transparent per feedback; status dot removed and replaced with expression-based busy/idle sprite swapping (hard-hat, magnifier, sleepy, alert, etc. from the extracted expression set) — supersedes Interface.md's original v1 scoping, SPEC.md updated (2026-07-21)
- Fix: sprite size wasn't locked to the world scene, only position was — `--sprite-w` and health-strip spacing used `vw` (viewport width) instead of the world container's own width, so sprites scaled out of proportion to the background whenever letterboxing changed. Fixed with CSS container queries (`cqw` instead of `vw`). Real "new build" modal replaces the `window.prompt` placeholder (2026-07-21)
- World/sprite polish: fixed a real sprite-drift bug (`.world`'s `background-size:cover` cropped differently at every window size since the container's aspect ratio didn't match the image — now locked to the backdrop's native ratio, verified at three window shapes); removed the stray sky artifact and unified the star field on one sparkle shape; extracted 19 expression-variant sprites from the reference sheet into `assets/characters/expressions/` (not wired into the app, v2 scope); composite scale test satisfied implicitly by every live screenshot already taken (2026-07-21)
- Nightshift accept-flow apply logic: `backend/nightshift/apply.py` parses and applies a proposal's `## Diff` section for real (was archive-only), fails safe (422, item stays pending) rather than guessing on an ambiguous or stale diff; distillation proposals now carry a cursor-advance marker so accepting one actually advances `lessons_distilled_through`. 11 new/updated tests, 87 passing. Verified live against the running backend (2026-07-21)
- Custos scoped-task launches: `POST /mode/{name}/jobs` gained a `notes` field (the actual job context.md prose, previously always empty); each lit trigger badge on Custos's card gets an "address" button, plus an always-available "run completeness check" action targeting Noctis OS's own SPEC.md/wiki. Custos still never runs on a schedule by design; this only scopes the on-demand launch (2026-07-21)
- Custos's trigger thresholds: `backend/triggers.py` computes friction/accumulation/suspicion live on every `GET /mode/settings` poll. Accumulation reuses nightshift's undistilled-lessons cursor; friction is an opt-in `FRICTION:` marker in lessons.md entries (documented in all five modes' lessons files); suspicion is a 7-day state.md staleness check. Resolves the Design Brief's last open item. Verified live end-to-end (2026-07-21)
- Security: first full ship-gate pass (dev.md's 9-step FINISH checklist) fixed stale README/CHANGELOG, and an 8-angle security-focused review found and fixed real path-traversal (unsanitized job slugs reaching filesystem paths), a hook-accumulation bug that defeated staleness flagging, missing per-item fault isolation in nightshift's run loop, an unlocked concurrent-write race on `state.md`, and an unanchored sentinel string match. `vault_io.py` now enforces path containment on every read/write and exposes `is_safe_slug()` for API-boundary validation. Verified live against the running backend with real attack payloads (2026-07-21)
- Fix: restore the locked typewriter-reveal entrance for profile-overlay card content — the card container had a fade/scale entrance, but the actual per-character content typing was never built (2026-07-21)
- Fix: vertically center idle-note text within the profile card body, was top-anchored via margin (2026-07-21)
- Fix: `load_dotenv()` in `main.py` — the backend only worked when the launching shell happened to have `.env` manually sourced; broke `make dev` silently otherwise (2026-07-21)
- Dev job lifecycle: `POST /mode/{name}/jobs` (create), `backend/staleness.py` (deterministic flag-on-death via a new `Stop` hook + 6h no-activity threshold, checked live on `GET /mode/dev`), per-job "resume" launch + new-build flow in the frontend. Closes the two gaps nightshift's own build exposed — no job ever got created, and `flagged` was silently dropped when syncing to `state.md` (2026-07-21)
- Nightshift infra: `backend/nightshift/{slack_surface,runner}.py` implement Scan (deterministic per-mode slack checks: dev's `flagged` jobs, settings' undistilled-lessons cursor) and Advance/Stage (dev is templated, settings borrows the distiller subagent via a real tool-scoped headless `claude -p` call); `scripts/nightshift_run.sh` + `launchd/com.noctis-os.nightshift.plist` wire it to a nightly launchd run. Closes out the locked Phase 3 build order (2026-07-21)
- Telemetry hooks: PostToolUse hook (`backend/hooks/log_action.py`) appends one action line per tool call to `backend/runtime/<mode>__<job>.log`; `PATCH /mode/{name}/jobs/{slug}` rewrites job-context frontmatter at stage transitions and syncs `state.md`; `GET /mode/{name}/jobs/{slug}/log` is the interface's poll target; ProfileOverlay's Faber job rows show a live last-action line (2026-07-21)
- Frontend tracker: `World.tsx` (real character sprites, live ambient state polling), `ProfileOverlay.tsx` (all five modes' locked card content), `api.ts` client, self-hosted fonts, `assets/` symlinked rather than duplicated. Fixed a missing-CORS bug and two sprite rendering bugs (opaque backgrounds, stray black column from a clamped-crop edge case) caught by actually running the app (2026-07-20/21)
- Backend: bearer-token + Origin auth, `vault_io.py` (frontmatter read/write, serialized writer for shared files), `GET /mode/{name}`, `POST /session/launch` (VS Code two-step for Dev, tinted Terminal.app + `CLAUDE_CONFIG_DIR` for the rest), nightshift inbox endpoints (2026-07-20)
- Mode folders: all five `second-brain/modes/<name>/` folders built (methodology, lessons, state, jobs, agents); `build-spine.md` migrated into `modes/dev/dev.md` as the one universal dev methodology (2026-07-20)
- Repo scaffolded: FastAPI + React/Vite, `.env.example`, `Makefile` (`setup`/`dev`), `SETUP.md` (2026-07-20)
- Spec drafted: Definition, PRD, EDD, Design Brief locked (2026-07-19/20)
