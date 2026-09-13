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
//!   2. **Coalesce reads before crossing the IPC.** Every chunk has to be
//!      serialised from Rust into the web view, and a fast-printing session
//!      makes hundreds of small reads a second. One event per read stalls; one
//!      frame per ~16ms does not.
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
    rows: u16,
    cols: u16,
) -> Result<(), String> {
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
    // The engine reads this the same way a `-p` spawn does, so the telemetry
    // hooks keep attributing actions to the right mode.
    if let Some(m) = args.iter().position(|a| a == "--noctis-mode") {
        if let Some(v) = args.get(m + 1) {
            cmd.env("NOCTIS_MODE", v);
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

    let emit_id = id.clone();
    std::thread::spawn(move || {
        let mut buf = [0u8; 65536];
        let mut pending: Vec<u8> = Vec::new();
        let mut last = Instant::now();
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    pending.extend_from_slice(&buf[..n]);
                    // Held only while the frame window is open. A burst
                    // arrives as one event; a lone keystroke echo still goes
                    // out within 16ms, so typing does not feel delayed.
                    if last.elapsed() >= FRAME {
                        let _ = app.emit(
                            "pty:data",
                            Chunk { id: emit_id.clone(), b64: STANDARD.encode(&pending) },
                        );
                        pending.clear();
                        last = Instant::now();
                    }
                }
            }
        }
        if !pending.is_empty() {
            let _ = app.emit(
                "pty:data",
                Chunk { id: emit_id.clone(), b64: STANDARD.encode(&pending) },
            );
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
