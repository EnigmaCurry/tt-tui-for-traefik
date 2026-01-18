use std::io;

use crossterm::{
    cursor,
    event::{self, Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{self, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    Terminal,
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::Line,
    widgets::{Block, Borders, Clear, Paragraph, Tabs},
};

use crate::{
    connection_monitor::{MonitorCmd, MonitorEvent, MonitorTarget, spawn_monitor},
    settings::{BasicAuth, ConnectionStatus, Settings},
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Focus {
    Top,
    Middle, // non-settings middle
    SettingsProfiles,
    SettingsDetails,
}

#[derive(Debug, Clone)]
enum Modal {
    ConfirmDelete {
        name: String,
        selected_yes: bool, // false = No (default)
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DetailField {
    Url,
    Username,
    Password,
}

impl DetailField {
    fn next(self) -> Self {
        match self {
            Self::Url => Self::Username,
            Self::Username => Self::Password,
            Self::Password => Self::Url,
        }
    }
    fn prev(self) -> Self {
        match self {
            Self::Url => Self::Password,
            Self::Username => Self::Url,
            Self::Password => Self::Username,
        }
    }
}

pub fn run() -> i32 {
    match run_inner() {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("TUI error: {e}");
            1
        }
    }
}

fn title_with_indent(title: &str, borders: Borders) -> String {
    if borders == Borders::NONE {
        format!(" {title}")
    } else {
        title.to_string()
    }
}

/// When borders are off, shift content right by one column to match the
/// usual "inside the border" indentation.
fn inner_with_indent(area: Rect, borders: Borders) -> Rect {
    if borders == Borders::NONE {
        Rect {
            x: area.x.saturating_add(1),
            width: area.width.saturating_sub(1),
            ..area
        }
    } else {
        area
    }
}

fn mask_password(pw: &str) -> String {
    if pw.is_empty() {
        "<empty>".to_string()
    } else {
        "*".repeat(pw.chars().count().min(64))
    }
}

fn truncate_25(s: &str) -> String {
    const MAX: usize = 25;
    let count = s.chars().count();
    if count <= MAX {
        return s.to_string();
    }
    let mut out: String = s.chars().take(MAX.saturating_sub(1)).collect();
    out.push('…');
    out
}

fn help_text(focus: Focus, tab: &str, tab_count: usize) -> String {
    let mut s = String::from("Tab: switch pane");

    match focus {
        Focus::Top => {
            if tab_count > 1 {
                s.push_str(" | \u{2190}/\u{2192}: select tab");
            }
        }
        Focus::SettingsProfiles => {
            s.push_str(" | \u{2191}/\u{2193}: select profile | Enter: add profile (todo)");
        }
        Focus::SettingsDetails => {
            s.push_str(" | \u{2191}/\u{2193}: select field | type to edit | Backspace: delete");
        }
        Focus::Middle => match tab {
            "Routers" => s.push_str(" | Routers: placeholder help"),
            "Services" => s.push_str(" | Services: placeholder help"),
            "Middleware" => s.push_str(" | Middleware: placeholder help"),
            _ => s.push_str(" | placeholder help"),
        },
    }

    s
}

fn is_printable_char(mods: KeyModifiers) -> bool {
    // allow typing unless ctrl/alt are held
    !mods.contains(KeyModifiers::CONTROL) && !mods.contains(KeyModifiers::ALT)
}

fn next_focus(current: Focus, settings_tab_selected: bool, has_profiles: bool) -> Focus {
    if settings_tab_selected {
        match current {
            Focus::Top => Focus::SettingsProfiles,
            Focus::SettingsProfiles => {
                if has_profiles {
                    Focus::SettingsDetails
                } else {
                    Focus::Top
                }
            }
            Focus::SettingsDetails => Focus::Top,
            Focus::Middle => Focus::Top,
        }
    } else {
        match current {
            Focus::Top => Focus::Middle,
            Focus::Middle => Focus::Top,
            Focus::SettingsProfiles | Focus::SettingsDetails => Focus::Top,
        }
    }
}

fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}

fn is_key_for_base(key: &str, base: &str) -> bool {
    if key == base {
        return true;
    }
    // Accept "base-<digits>"
    if let Some(suffix) = key.strip_prefix(base).and_then(|s| s.strip_prefix('-')) {
        return !suffix.is_empty() && suffix.chars().all(|c| c.is_ascii_digit());
    }
    false
}

fn maybe_rename_selected_profile(settings: &mut Settings, dirty: &mut bool) {
    let Some(old) = settings.selected_name().map(|s| s.to_string()) else {
        return;
    };
    let Some(p) = settings.selected_profile() else {
        return;
    };

    let Some(base) = Settings::profile_key_from_url(&p.url) else {
        return;
    };

    // If the current key is already the base or base-<n>, do nothing.
    if is_key_for_base(&old, &base) {
        return;
    }

    if settings.rename_profile(&old, &base).is_some() {
        *dirty = true;
    }
}

fn save_if_dirty(settings: &Settings, dirty: &mut bool) {
    if *dirty {
        let _ = settings.save();
        *dirty = false;
    }
}

fn ensure_basic_auth_profile(p: &mut crate::settings::Profile) -> &mut BasicAuth {
    if p.basic_auth.is_none() {
        p.basic_auth = Some(BasicAuth {
            username: String::new(),
            password: String::new(),
        });
    }
    p.basic_auth.as_mut().expect("just initialized")
}

fn run_inner() -> io::Result<()> {
    let mut stdout = io::stdout();

    terminal::enable_raw_mode()?;
    execute!(stdout, EnterAlternateScreen, cursor::Hide)?;

    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Ensure we always restore terminal state.
    let _guard = TerminalGuard;

    let mut focus = Focus::Top;

    // Load settings/config (fallback to defaults on error for now)
    let mut settings = Settings::load_or_default().unwrap_or_default();
    let mut dirty = false;

    // Which tab is selected (index into current tab list)
    let mut selected_tab: usize = 0;

    // Which field is selected in Settings details pane
    let mut detail_field = DetailField::Url;
    let mut modal: Option<Modal> = None;

    let (mon_tx, mon_rx, mon_handle) = spawn_monitor();
    let mut last_target_sig: Option<String> = None;

    loop {
        // Build a stable list of profile names for navigation.
        let profile_names: Vec<String> = settings.profiles.keys().cloned().collect();
        // If there are no profiles, don't allow Details focus
        let has_profiles = !profile_names.is_empty();
        if !has_profiles && focus == Focus::SettingsDetails {
            focus = Focus::SettingsProfiles;
        }

        // Drain monitor events
        while let Ok(evt) = mon_rx.try_recv() {
            match evt {
                MonitorEvent::Update {
                    name,
                    status,
                    version,
                } => {
                    let rt = settings.runtime_for_mut(&name);
                    rt.status = status;
                    rt.version = version;
                }
            }
        }

        let target = settings.selected_name().and_then(|name| {
            settings.profiles.get(name).map(|p| {
                let (username, password) = match &p.basic_auth {
                    Some(a) => (Some(a.username.clone()), Some(a.password.clone())),
                    None => (None, None),
                };
                MonitorTarget {
                    name: name.to_string(),
                    base_url: p.url.clone(),
                    username,
                    password,
                }
            })
        });

        let sig = target.as_ref().map(|t| {
            format!(
                "{}|{}|{}|{}",
                t.name,
                t.base_url,
                t.username.as_deref().unwrap_or(""),
                t.password.as_deref().unwrap_or("")
            )
        });

        // Send only when changed
        if sig != last_target_sig {
            let _ = mon_tx.send(MonitorCmd::SetTarget(target));
            last_target_sig = sig;
        }

        // Determine selected profile & connection state (placeholder runtime status)
        let selected_name = settings.selected_name().unwrap_or("");
        let connected = if !selected_name.is_empty() {
            settings.runtime_for(selected_name).status == ConnectionStatus::Connected
        } else {
            false
        };

        // Dynamic tabs based on connection status.
        let tab_names: &[&str] = if connected {
            &["Settings", "Routers", "Services", "Middleware"]
        } else {
            &["Settings"]
        };

        if selected_tab >= tab_names.len() {
            selected_tab = 0;
        }

        let is_settings_tab = tab_names[selected_tab] == "Settings";

        // If we switched away from Settings, normalize focus.
        if !is_settings_tab && matches!(focus, Focus::SettingsProfiles | Focus::SettingsDetails) {
            focus = Focus::Middle;
        }

        terminal.draw(|f| {
            let area = f.area();
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(4), // top (tabs + status)
                    Constraint::Min(0),    // middle
                    Constraint::Length(1), // bottom (help)
                ])
                .split(area);

            // --- Top block (title + tabs row + status row) ---
            let top_borders = if focus == Focus::Top {
                Borders::ALL
            } else {
                Borders::NONE
            };

            let top_block = Block::default()
                .borders(top_borders)
                .title(title_with_indent("tt-tui-for-traefik", top_borders));

            f.render_widget(top_block.clone(), chunks[0]);

            let top_inner = inner_with_indent(top_block.inner(chunks[0]), top_borders);
            let top_rows = Layout::default()
                .direction(Direction::Vertical)
                .constraints([Constraint::Length(1), Constraint::Length(1)])
                .split(top_inner);

            let tab_titles: Vec<Line> = tab_names.iter().map(|t| Line::from(*t)).collect();
            let tabs = Tabs::new(tab_titles)
                .select(selected_tab)
                .highlight_style(Style::default().add_modifier(Modifier::BOLD));
            f.render_widget(tabs, top_rows[0]);

            // let status = if connected {
            //     "Status: Connected."
            // } else {
            //     "Status: Disconnected."
            // };
            // f.render_widget(Paragraph::new(status), top_rows[1]);

            // --- Middle area ---
            let middle_title = tab_names[selected_tab];

            if is_settings_tab {
                // Settings page: split left/right inside middle area
                let cols = Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([Constraint::Length(35), Constraint::Min(0)])
                    .split(chunks[1]);

                // Left: profiles list (max 25 chars each)
                let left_borders = if focus == Focus::SettingsProfiles {
                    Borders::ALL
                } else {
                    Borders::NONE
                };
                let left_block = Block::default()
                    .borders(left_borders)
                    .title(title_with_indent("Profiles", left_borders));
                f.render_widget(left_block.clone(), cols[0]);
                let left_inner = inner_with_indent(left_block.inner(cols[0]), left_borders);

                let mut left_text = String::new();
                if profile_names.is_empty() {
                    left_text.push_str("<no profiles>\n");
                } else {
                    for name in &profile_names {
                        let prefix = if settings.selected_name() == Some(name.as_str()) {
                            "> "
                        } else {
                            "  "
                        };
                        left_text.push_str(prefix);
                        if let Some(p) = settings.profiles.get(name) {
                            left_text.push_str(&truncate_25(&name));
                        } else {
                            left_text.push_str(&truncate_25(name));
                        }

                        left_text.push('\n');
                    }
                }
                left_text.push('\n');
                if focus == Focus::SettingsProfiles {
                    left_text.push_str("Press C to create new profile.\n");
                    left_text.push_str("Press DEL to remove profile.\n");
                }
                f.render_widget(Paragraph::new(left_text), left_inner);

                // Right: details editor
                let right_borders = if focus == Focus::SettingsDetails {
                    Borders::ALL
                } else {
                    Borders::NONE
                };
                let right_block = Block::default()
                    .borders(right_borders)
                    .title(title_with_indent("Details", right_borders));
                f.render_widget(right_block.clone(), cols[1]);
                let right_inner = inner_with_indent(right_block.inner(cols[1]), right_borders);

                if !has_profiles {
                    // Explicitly show nothing (or you can put a very small hint string)
                    // f.render_widget(Paragraph::new(""), right_inner);
                } else {
                    let sel = settings.selected_name().unwrap_or("").to_string();
                    let profile = settings.selected_profile();

                    let (url, username, pw_masked) = match profile {
                        Some(p) => {
                            let (u, pw) = match &p.basic_auth {
                                Some(auth) => (auth.username.as_str(), auth.password.as_str()),
                                None => ("", ""),
                            };
                            (p.url.as_str(), u, mask_password(pw))
                        }
                        None => ("", "", "<none>".to_string()),
                    };

                    let rt = settings
                        .selected_name()
                        .map(|n| settings.runtime_for(n))
                        .unwrap_or_default();

                    let status_text = match rt.status {
                        ConnectionStatus::Connected => "Connected",
                        ConnectionStatus::Disconnected => "Disconnected",
                    };
                    let version_text = rt.version.as_deref().unwrap_or("-");

                    let mut right_text = String::new();
                    right_text.push_str(&format!("Profile: {sel}\n\n"));

                    let marker = |field: DetailField, current: DetailField| {
                        if field == current { "> " } else { "  " }
                    };

                    right_text.push_str(marker(DetailField::Url, detail_field));
                    right_text.push_str(&format!("URL: {url}\n"));

                    right_text.push_str(marker(DetailField::Username, detail_field));
                    right_text.push_str(&format!(
                        "Username: {}\n",
                        if username.is_empty() {
                            "<none>"
                        } else {
                            username
                        }
                    ));

                    right_text.push_str(marker(DetailField::Password, detail_field));
                    right_text.push_str(&format!("Password: {pw_masked}\n\n"));

                    right_text.push_str(&format!("Status: {status_text}\n"));
                    right_text.push_str(&format!("Version: {version_text}\n"));

                    f.render_widget(Paragraph::new(right_text), right_inner);
                }
            } else {
                // Non-settings pages: single middle pane with focus border behavior
                let middle_borders = if focus == Focus::Middle {
                    Borders::ALL
                } else {
                    Borders::NONE
                };
                let middle_block = Block::default()
                    .borders(middle_borders)
                    .title(title_with_indent(middle_title, middle_borders));
                f.render_widget(middle_block.clone(), chunks[1]);
                let inner = inner_with_indent(middle_block.inner(chunks[1]), middle_borders);
                f.render_widget(Paragraph::new("TODO"), inner);
            }

            // --- Bottom help (contextual) ---
            let help = help_text(focus, middle_title, tab_names.len());
            f.render_widget(Paragraph::new(help), chunks[2]);

            // --- Modal overlay (delete confirm) ---
            if let Some(Modal::ConfirmDelete { name, selected_yes }) = &modal {
                let area = centered_rect(60, 20, f.area());

                f.render_widget(Clear, area);

                let block = Block::default()
                    .borders(Borders::ALL)
                    .title(" Confirm delete ");

                f.render_widget(block.clone(), area);

                let question = format!("Do you really want to delete profile {name} ?");

                let yes_style = if *selected_yes {
                    Style::default().add_modifier(Modifier::BOLD)
                } else {
                    Style::default()
                };
                let no_style = if !*selected_yes {
                    Style::default().add_modifier(Modifier::BOLD)
                } else {
                    Style::default()
                };

                // Simple text "buttons" on one line.
                let buttons =
                    Line::from(vec!["  ".into(), "Yes".into(), "   ".into(), "No".into()]);

                // We’ll render the question + buttons manually with Paragraph.
                // To keep it simple without spans styling, we show selection via brackets.
                let yes = if *selected_yes { "[Yes]" } else { " Yes " };
                let no = if !*selected_yes { "[No]" } else { " No " };

                let text = format!("{question}\n\n   {yes}     {no}");

                f.render_widget(Paragraph::new(text), block.inner(area));
            }
        })?;

        // Input handling
        if event::poll(std::time::Duration::from_millis(250))? {
            match event::read()? {
                Event::Key(k) if matches!(k.kind, KeyEventKind::Press | KeyEventKind::Repeat) => {
                    // quitting should flush any pending edits
                    let quit = matches!(k.code, KeyCode::Char('q') | KeyCode::Esc)
                        || (k.code == KeyCode::Char('c')
                            && k.modifiers.contains(KeyModifiers::CONTROL));
                    if quit {
                        maybe_rename_selected_profile(&mut settings, &mut dirty);
                        save_if_dirty(&settings, &mut dirty);
                        let _ = mon_tx.send(MonitorCmd::Stop);
                        let _ = mon_handle.join();
                        break;
                    }

                    // If a modal is open, it consumes keys (prevents accidental focus/selection changes)
                    if let Some(active) = modal.clone() {
                        match active {
                            Modal::ConfirmDelete {
                                name,
                                mut selected_yes,
                            } => match k.code {
                                KeyCode::Left | KeyCode::Right | KeyCode::Tab => {
                                    selected_yes = !selected_yes;
                                    modal = Some(Modal::ConfirmDelete { name, selected_yes });
                                }
                                KeyCode::Enter => {
                                    if selected_yes {
                                        maybe_rename_selected_profile(&mut settings, &mut dirty);
                                        save_if_dirty(&settings, &mut dirty);

                                        let _ = settings.remove_profile(&name);
                                        dirty = true;
                                        save_if_dirty(&settings, &mut dirty);
                                    }
                                    modal = None;
                                }
                                KeyCode::Esc => {
                                    modal = None;
                                }
                                KeyCode::Char('y') | KeyCode::Char('Y') => {
                                    maybe_rename_selected_profile(&mut settings, &mut dirty);
                                    save_if_dirty(&settings, &mut dirty);

                                    let _ = settings.remove_profile(&name);
                                    dirty = true;
                                    save_if_dirty(&settings, &mut dirty);

                                    modal = None;
                                }
                                KeyCode::Char('n') | KeyCode::Char('N') => {
                                    modal = None;
                                }
                                _ => {}
                            },
                        }
                        continue;
                    }

                    match k.code {
                        KeyCode::Delete if focus == Focus::SettingsProfiles && has_profiles => {
                            if let Some(name) = settings.selected_name() {
                                modal = Some(Modal::ConfirmDelete {
                                    name: name.to_string(),
                                    selected_yes: false,
                                });
                            }
                        }
                        KeyCode::Tab => {
                            if focus == Focus::SettingsDetails {
                                maybe_rename_selected_profile(&mut settings, &mut dirty);
                                save_if_dirty(&settings, &mut dirty);
                            }

                            let current_is_settings = tab_names[selected_tab] == "Settings";
                            focus = next_focus(focus, current_is_settings, has_profiles);
                        }

                        // Top focus: move between tabs (only if there is >1 tab)
                        KeyCode::Left if focus == Focus::Top && tab_names.len() > 1 => {
                            maybe_rename_selected_profile(&mut settings, &mut dirty);
                            save_if_dirty(&settings, &mut dirty);
                            if selected_tab == 0 {
                                selected_tab = tab_names.len() - 1;
                            } else {
                                selected_tab -= 1;
                            }
                        }
                        KeyCode::Right if focus == Focus::Top && tab_names.len() > 1 => {
                            maybe_rename_selected_profile(&mut settings, &mut dirty);
                            save_if_dirty(&settings, &mut dirty);
                            selected_tab = (selected_tab + 1) % tab_names.len();
                        }

                        // Settings: profiles list navigation
                        KeyCode::Up if focus == Focus::SettingsProfiles => {
                            if !profile_names.is_empty() {
                                maybe_rename_selected_profile(&mut settings, &mut dirty);
                                save_if_dirty(&settings, &mut dirty);
                                let cur = settings
                                    .selected_name()
                                    .and_then(|n| profile_names.iter().position(|p| p == n))
                                    .unwrap_or(0);

                                let next = if cur == 0 {
                                    profile_names.len() - 1
                                } else {
                                    cur - 1
                                };
                                settings.set_selected(&profile_names[next]);
                            }
                        }
                        KeyCode::Down if focus == Focus::SettingsProfiles => {
                            if !profile_names.is_empty() {
                                maybe_rename_selected_profile(&mut settings, &mut dirty);
                                save_if_dirty(&settings, &mut dirty);

                                let cur = settings
                                    .selected_name()
                                    .and_then(|n| profile_names.iter().position(|p| p == n))
                                    .unwrap_or(0);

                                let next = (cur + 1) % profile_names.len();
                                settings.set_selected(&profile_names[next]);
                            }
                        }

                        // Settings: details field selection
                        KeyCode::Up if focus == Focus::SettingsDetails => {
                            save_if_dirty(&settings, &mut dirty); // blur previous field
                            detail_field = detail_field.prev();
                        }
                        KeyCode::Down if focus == Focus::SettingsDetails => {
                            save_if_dirty(&settings, &mut dirty); // blur previous field
                            detail_field = detail_field.next();
                        }

                        // Settings: typing into fields (auto-save on blur; here we mark dirty)
                        KeyCode::Backspace if focus == Focus::SettingsDetails => {
                            if let Some(p) = settings.selected_profile_mut() {
                                match detail_field {
                                    DetailField::Url => {
                                        p.url.pop();
                                        dirty = true;
                                    }
                                    DetailField::Username => {
                                        let auth = ensure_basic_auth_profile(p);
                                        auth.username.pop();
                                        dirty = true;
                                    }
                                    DetailField::Password => {
                                        let auth = ensure_basic_auth_profile(p);
                                        auth.password.pop();
                                        dirty = true;
                                    }
                                }
                            }
                        }

                        KeyCode::Char('c') | KeyCode::Char('C')
                            if focus == Focus::SettingsProfiles =>
                        {
                            save_if_dirty(&settings, &mut dirty);
                            let _new_name = settings.add_profile("new");
                            dirty = true;
                            save_if_dirty(&settings, &mut dirty);
                        }
                        KeyCode::Char(c)
                            if focus == Focus::SettingsDetails
                                && is_printable_char(k.modifiers) =>
                        {
                            if let Some(p) = settings.selected_profile_mut() {
                                match detail_field {
                                    DetailField::Url => {
                                        p.url.push(c);
                                        dirty = true;
                                    }
                                    DetailField::Username => {
                                        let auth = ensure_basic_auth_profile(p);
                                        auth.username.push(c);
                                        dirty = true;
                                    }
                                    DetailField::Password => {
                                        let auth = ensure_basic_auth_profile(p);
                                        auth.password.push(c);
                                        dirty = true;
                                    }
                                }
                            }
                        }

                        _ => {}
                    }
                }
                Event::Resize(_, _) => {}
                _ => {}
            }
        }
    }

    Ok(())
}

struct TerminalGuard;

impl Drop for TerminalGuard {
    fn drop(&mut self) {
        let _ = terminal::disable_raw_mode();
        let mut stdout = io::stdout();
        let _ = execute!(stdout, LeaveAlternateScreen, cursor::Show);
    }
}
