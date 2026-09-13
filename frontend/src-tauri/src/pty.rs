//! Hosting a real interactive Claude Code session.
//!
//! Noctis has driven `claude -p` -- "print response and exit" in the CLI's own
//! help -- once per turn, and rebuilt the interactive loop on top of it: the
//! closing pass, the permission host, per-turn respawn. This runs the CLI the
//! way a terminal does instead, and the reconstruction stops being needed.
//!
//! Three things this file has to get right, all found by testing rather than
//! reasoning (see `PTY-MIGRATION.md` §3):
//!
//!   1. **Size the PTY before spawning.** At 0x0 the TUI exits instantly with
//!      no error and no output, which reads exactly like "PTY doesn't work
//!      here". It cost the first spike run.
//!   2. **Coalesce reads before crossing the IPC -- and flush on silence.**
//!      Every chunk has to be serialised from Rust into the web view, and a
//!      fast-printing session makes hundreds of small reads a second. One
//!      event per read stalls; one frame per ~16ms does not. But a flush that
//!      only runs when the *next* read arrives strands the last frame of a
//!      prompt that then blocks for input -- the trust dialog rendered to
//!      mid-sentence and stopped until a keystroke made the CLI repaint. So a
//!      quiet frame sends what it holds, which takes a second thread.
//!   3. **Kill the whole session, not the process.** Same lesson the pywebview
//!      shell taught in July: the immediate child is not the only thing
//!      holding the terminal.
//!
//! Bytes travel base64-encoded rather than as a string. A read can split a
//! multi-byte character down the middle, and xterm.js has its own UTF-8
//! decoder that handles the seam -- decoding early here would corrupt it.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, State};

/// How long output is gathered before one frame is sent. Roughly a display
/// frame: below this the web view cannot show the difference, above it the
/// terminal feels like it is lagging behind the keyboard.
const FRAME: Duration = Duration::from_millis(16);

/// Where `claude` is looked for when PATH does not have it. Mirrors
/// `backend/orchestrator/driver.py`'s list, and for the same reason: a
/// process started by launchd or by Finder gets a bare PATH with no Homebrew.
const FALLBACKS: [&str; 4] = [
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "~/.local/bin/claude",
    "~/.claude/local/claude",
];

pub struct Session {
    master: Box<dyn MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    child: Box<dyn portable_pty::Child + Send + Sync>,
}

#[derive(Default)]
pub struct Ptys(pub Arc<Mutex<HashMap<String, Session>>>);

#[derive(Clone, Serialize)]
struct Chunk {
    id: String,
    /// base64; see the module note on why this is not a string.
    b64: String,
}

#[derive(Clone, Serialize)]
struct Exit {
    id: String,
    code: Option<u32>,
}

fn resolve_binary(explicit: Option<String>) -> String {
    if let Some(p) = explicit.filter(|p| !p.is_empty()) {
        return p;
    }
    if let Ok(path) = std::env::var("PATH") {
        for dir in path.split(':') {
            let c = std::path::Path::new(dir).join("claude");
            if c.is_file() {
                return c.to_string_lossy().into_owned();
            }
        }
    }
    for f in FALLBACKS {
        let expanded = if let Some(rest) = f.strip_prefix("~/") {
            match std::env::var("HOME") {
                Ok(home) => format!("{home}/{rest}"),
                Err(_) => continue,
            }
        } else {
            f.to_string()
        };
        if std::path::Path::new(&expanded).is_file() {
            return expanded;
        }
    }
    // Returned rather than erroring, so the failure surfaces as a spawn error
    // naming what was tried instead of a bare errno.
    "claude".into()
}

/// Start a session. `args` comes from the backend, which owns the mode ->
/// methodology mapping; this file deliberately knows nothing about modes.
#[tauri::command]
pub fn pty_spawn(
    app: AppHandle,
    state: State<'_, Ptys>,
    id: String,
    cwd: String,
    args: Vec<String>,
    binary: Option<String>,
    env: Option<HashMap<String, String>>,
    rows: u16,
    cols: u16,
) -> Result<(), String> {
    // Replacing rather than stacking. React's StrictMode mounts, unmounts and
    // mounts again in development, so this id can arrive twice; without the
    // reap the second insert would drop the first Session's handle on the
    // floor and leave its engine running with nothing reading it. Same leak
    // the pywebview shell taught in July, in a new place.
    if let Some(mut old) = state
        .0
        .lock()
        .map_err(|_| "pty registry poisoned".to_string())?
        .remove(&id)
    {
        let _ = old.child.kill();
        let _ = old.child.wait();
    }

    let pty = native_pty_system();
    // Before the spawn. See the module note -- this is not incidental ordering.
    let size = PtySize {
        rows: rows.max(2),
        cols: cols.max(20),
        pixel_width: 0,
        pixel_height: 0,
    };
    let pair = pty.openpty(size).map_err(|e| format!("openpty: {e}"))?;

    let bin = resolve_binary(binary);
    let mut cmd = CommandBuilder::new(&bin);
    for a in &args {
        cmd.arg(a);
    }
    cmd.cwd(&cwd);
    cmd.env("TERM", "xterm-256color");
    // The environment the backend asked for, beside the argv it asked for.
    // NOCTIS_MODE and NOCTIS_JOB_ID are what the telemetry hooks read to
    // attribute an action to a mode and a job; a PTY child otherwise
    // inherits *this* process's environment, and a vesper session was
    // logging under whatever mode the shell happened to have. The first
    // version scanned the argv for a `--noctis-mode` flag the backend never
    // sent -- and which the engine would have rejected if it had.
    if let Some(vars) = env {
        for (k, v) in vars {
            cmd.env(k, v);
        }
    }

    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("could not start engine {bin:?}: {e}"))?;
    drop(pair.slave);

    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("reader: {e}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|e| format!("writer: {e}"))?;

    // Two threads, because a blocking read cannot also keep time.
    //
    // The first version batched inside the read loop: extend `pending`, and
    // flush if a frame had elapsed. That flushes only when *another read
    // arrives* -- so when the CLI finished painting its prompt and blocked
    // waiting for input, the tail of that prompt sat in `pending` with nothing
    // to trigger sending it. The trust dialog rendered up to mid-sentence and
    // stopped; pressing ↓ made the CLI repaint, which produced a read, which
    // shook the rest loose. Silence has to flush too, and a thread parked in
    // `read()` cannot notice silence. So the reader only reads, and the
    // batcher waits on a channel with a deadline: data extends the frame,
    // and a frame with no data sends what it has.
    let (tx, rx) = std::sync::mpsc::channel::<Vec<u8>>();
    std::thread::spawn(move || {
        let mut buf = [0u8; 65536];
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    if tx.send(buf[..n].to_vec()).is_err() {
                        break;
                    }
                }
            }
        }
        // Dropping `tx` is the exit signal: the batcher sees Disconnected.
    });

    let emit_id = id.clone();
    std::thread::spawn(move || {
        use std::sync::mpsc::RecvTimeoutError::{Disconnected, Timeout};
        let mut pending: Vec<u8> = Vec::new();
        let mut opened = Instant::now();
        let flush = |pending: &mut Vec<u8>| {
            if !pending.is_empty() {
                let _ = app.emit(
                    "pty:data",
                    Chunk { id: emit_id.clone(), b64: STANDARD.encode(&pending) },
                );
                pending.clear();
            }
        };
        loop {
            match rx.recv_timeout(FRAME) {
                Ok(chunk) => {
                    if pending.is_empty() {
                        opened = Instant::now();
                    }
                    pending.extend_from_slice(&chunk);
                    // A burst keeps arriving inside the window; it still goes
                    // out once the window is a frame old, so a long build log
                    // streams at frame rate rather than accumulating until a
                    // pause. Without this bound a fast printer would only
                    // ever flush on `Timeout`, which it never reaches.
                    if opened.elapsed() >= FRAME {
                        flush(&mut pending);
                    }
                }
                // Nothing for a frame: whatever is held is complete for now.
                // This is the branch the first version did not have.
                Err(Timeout) => flush(&mut pending),
                Err(Disconnected) => {
                    flush(&mut pending);
                    break;
                }
            }
        }
        let _ = app.emit("pty:exit", Exit { id: emit_id, code: None });
    });

    state
        .0
        .lock()
        .map_err(|_| "pty registry poisoned".to_string())?
        .insert(id, Session { master: pair.master, writer, child });
    Ok(())
}

#[tauri::command]
pub fn pty_write(state: State<'_, Ptys>, id: String, data: String) -> Result<(), String> {
    let mut map = state.0.lock().map_err(|_| "pty registry poisoned".to_string())?;
    let s = map.get_mut(&id).ok_or("no such session")?;
    s.writer.write_all(data.as_bytes()).map_err(|e| e.to_string())?;
    s.writer.flush().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn pty_resize(state: State<'_, Ptys>, id: String, rows: u16, cols: u16) -> Result<(), String> {
    let map = state.0.lock().map_err(|_| "pty registry poisoned".to_string())?;
    let s = map.get(&id).ok_or("no such session")?;
    s.master
        .resize(PtySize { rows: rows.max(2), cols: cols.max(20), pixel_width: 0, pixel_height: 0 })
        .map_err(|e| e.to_string())
}

/// Stop a session and forget it. Idempotent: closing a tab twice, or closing
/// one whose process already exited, is not an error worth surfacing.
#[tauri::command]
pub fn pty_kill(state: State<'_, Ptys>, id: String) -> Result<(), String> {
    let mut map = state.0.lock().map_err(|_| "pty registry poisoned".to_string())?;
    if let Some(mut s) = map.remove(&id) {
        let _ = s.child.kill();
        let _ = s.child.wait();
    }
    Ok(())
}

/// Which sessions are live. The shell reads this after a reload to know what
/// it is reattaching to rather than assuming its own memory is right.
#[tauri::command]
pub fn pty_list(state: State<'_, Ptys>) -> Result<Vec<String>, String> {
    Ok(state
        .0
        .lock()
        .map_err(|_| "pty registry poisoned".to_string())?
        .keys()
        .cloned()
        .collect())
}
