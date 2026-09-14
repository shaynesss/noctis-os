//! Noctis desktop shell — Stage 2 item 4.
//!
//! The shell exists for one reason: **being one keystroke away.** v2's whole
//! premise is that mode entry has a context cost and Desktop has none, so the
//! fallback wins. A window you have to go and find has not fixed that.
//!
//! v1 rejected Tauri on 2026-07-21 — correctly, for what v1 was. v1 was a
//! *launcher*, so native OS integration bought nothing. v2 is the *front
//! door*, which makes global hotkey summon, tray presence and launch-at-login
//! load-bearing rather than polish. That is the reason recorded in the spec
//! for overriding the earlier decision.

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Manager, WindowEvent,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

mod pty;

/// Opt+Space. Chosen over Cmd-anything because the summon has to work while
/// another app has focus, and the Cmd space is crowded with per-app bindings
/// it would silently shadow.
///
/// A function rather than a const: `Shortcut::new` is not const, so a const
/// binding does not compile.
fn summon() -> Shortcut {
    Shortcut::new(Some(Modifiers::ALT), Code::Space)
}

/// Show and focus, or hide if already frontmost.
///
/// Toggling rather than only showing is what makes the hotkey usable at
/// speed: the same key gets you in and out, so summoning is not a decision
/// about whether the window is already open.
fn toggle(app: &AppHandle) {
    let Some(win) = app.get_webview_window("main") else {
        return;
    };
    let visible = win.is_visible().unwrap_or(false);
    let focused = win.is_focused().unwrap_or(false);

    if visible && focused {
        let _ = win.hide();
    } else {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "Show Noctis", true, Some("Alt+Space"))?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    TrayIconBuilder::with_id("noctis")
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .show_menu_on_left_click(false) // left click summons; the menu is the right-click affordance
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => toggle(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let tauri::tray::TrayIconEvent::Click {
                button: tauri::tray::MouseButton::Left,
                button_state: tauri::tray::MouseButtonState::Up,
                ..
            } = event
            {
                toggle(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

/// Open a link in the person's browser.
///
/// The webview does not honour `target="_blank"`: a link to a pull request
/// clicked in the Repo view did nothing at all. macOS's own `open` is the
/// whole implementation -- no plugin, no capability file entry -- and it is
/// limited to http(s), because `open` will also run a file or an app.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err("only http(s) links open".into());
    }
    std::process::Command::new("open")
        .arg(&url)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(pty::Ptys::default())
        .invoke_handler(tauri::generate_handler![
            pty::pty_spawn,
            pty::pty_write,
            pty::pty_resize,
            pty::pty_kill,
            pty::pty_list,
            pty::pty_attach,
            open_url,
        ])
        .plugin(tauri_plugin_notification::init())
        // Read-image only, by the capability file. The shell checks whether
        // an image is waiting so the composer can offer to paste it; it
        // never reads clipboard text, which is where passwords and tokens
        // pass through.
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    // Fire on press only. Without the guard the toggle runs
                    // twice per keypress and the window flickers shut again.
                    if shortcut == &summon() && event.state() == ShortcutState::Pressed {
                        toggle(app);
                    }
                })
                .build(),
        )
        .setup(|app| {
            let handle = app.handle();
            app.global_shortcut().register(summon())?;
            build_tray(handle)?;

            // Shown explicitly rather than via the config's `visible` flag:
            // the window is created hidden so it never paints an unstyled
            // frame before the web view has content, which is the flash you
            // get when a shell shows itself first and loads second.
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.show();
                let _ = win.set_focus();
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing hides rather than quits. An always-there app that exits
            // on the close button is not always there -- and the tray plus the
            // hotkey are the ways back, so nothing is stranded.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Noctis");
}
