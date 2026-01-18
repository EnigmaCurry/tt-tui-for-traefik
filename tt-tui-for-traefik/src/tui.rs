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
    layout::{Constraint, Direction, Layout},
    widgets::{Block, Borders},
};

pub fn run() -> i32 {
    match run_inner() {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("TUI error: {e}");
            1
        }
    }
}

fn run_inner() -> io::Result<()> {
    let mut stdout = io::stdout();

    terminal::enable_raw_mode()?;
    execute!(stdout, EnterAlternateScreen, cursor::Hide)?;

    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Ensure we always restore terminal state.
    let _guard = TerminalGuard;

    loop {
        terminal.draw(|f| {
            let area = f.area();
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(2), // top
                    Constraint::Min(0),    // middle (fills)
                    Constraint::Length(1), // bottom
                ])
                .split(area);

            f.render_widget(
                Block::default().borders(Borders::ALL).title("top"),
                chunks[0],
            );
            f.render_widget(
                Block::default().borders(Borders::ALL).title("middle"),
                chunks[1],
            );
            f.render_widget(
                Block::default().borders(Borders::ALL).title("bottom"),
                chunks[2],
            );
        })?;

        // Input handling
        if event::poll(std::time::Duration::from_millis(250))? {
            match event::read()? {
                Event::Key(k) if k.kind == KeyEventKind::Press => {
                    let quit = matches!(k.code, KeyCode::Char('q') | KeyCode::Esc)
                        || (k.code == KeyCode::Char('c')
                            && k.modifiers.contains(KeyModifiers::CONTROL));
                    if quit {
                        break;
                    }
                }
                Event::Resize(_, _) => {} // redraw happens automatically next loop
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
