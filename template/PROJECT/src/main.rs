use clap_complete::shells::Shell;
use std::env;
use std::io::Write;

mod cli;
mod prelude;

use prelude::*;

pub fn run_cli<I, S, W1, W2>(args: I, out: &mut W1, err: &mut W2) -> i32
where
    I: IntoIterator<Item = S>,
    S: Into<std::ffi::OsString> + Clone,
    W1: Write,
    W2: Write,
{
    let cmd = cli::app();
    let matches = match cmd.clone().try_get_matches_from(args) {
        Ok(m) => m,
        Err(e) => {
            let _ = write!(err, "{e}");
            return 2;
        }
    };

    dispatch(cmd, matches, out, err)
}

fn main() {
    let code = run_cli(
        std::env::args_os(),
        &mut std::io::stdout(),
        &mut std::io::stderr(),
    );
    std::process::exit(code);
}

fn dispatch<W1, W2>(
    mut cmd: clap::Command,
    matches: clap::ArgMatches,
    out: &mut W1,
    err: &mut W2,
) -> i32
where
    W1: Write,
    W2: Write,
{
    init_logging(&matches);

    // Print help if no subcommand is given.
    if matches.subcommand_name().is_none() {
        let _ = cmd.write_help(out);
        let _ = writeln!(out);
        return 0;
    }

    match matches.subcommand() {
        Some(("hello", sub_matches)) => hello(sub_matches, out, err),
        Some(("completions", sub_matches)) => completions(sub_matches, out, err),
        _ => 1,
    }
}

fn init_logging(matches: &clap::ArgMatches) {
    use std::str::FromStr;

    let log_level = if matches.get_flag("verbose") {
        Some("debug".to_string())
    } else {
        matches.get_one::<String>("log").cloned()
    };

    let log_level = log_level.or_else(|| std::env::var("RUST_LOG").ok());
    let log_level = log_level.unwrap_or_else(|| "info".to_string());

    let mut builder = env_logger::Builder::new();
    builder
        .filter_level(log::LevelFilter::from_str(&log_level).unwrap_or(log::LevelFilter::Info))
        .format_timestamp(None);

    // Avoid panicking in tests if a logger is already set.
    let _ = builder.try_init();

    debug!("logging initialized.");
}

fn hello<W1: Write, W2: Write>(sub_matches: &clap::ArgMatches, out: &mut W1, err: &mut W2) -> i32 {
    let arg_name = sub_matches
        .get_one::<String>("NAME")
        .map(|s| s.trim())
        .filter(|s| !s.is_empty());

    let env_user = env::var("USER")
        .or_else(|_| env::var("USERNAME"))
        .unwrap_or_else(|_| "<unknown>".into());

    let name = arg_name.unwrap_or(env_user.as_str());

    let _ = writeln!(out, "Hello, {name}!");

    match env::current_dir() {
        Ok(path) => {
            let _ = writeln!(out, "Current working dir: {}", path.display());
        }
        Err(e) => {
            let _ = writeln!(err, "Failed to get current dir: {e}");
        }
    }

    0
}

fn completions<W1: Write, W2: Write>(
    sub_matches: &clap::ArgMatches,
    out: &mut W1,
    err: &mut W2,
) -> i32 {
    if let Some(shell) = sub_matches.get_one::<String>("shell") {
        match shell.as_str() {
            "bash" => generate_completion_script(Shell::Bash, out),
            "zsh" => generate_completion_script(Shell::Zsh, out),
            "fish" => generate_completion_script(Shell::Fish, out),
            shell => {
                let _ = writeln!(err, "Unsupported shell: {shell}");
                return 1;
            }
        }
        0
    } else {
        let bin = env!("CARGO_BIN_NAME");

        let _ = writeln!(err, "### Instructions to enable tab completion for {bin}\n");
        let _ = writeln!(err, "### Bash (put this in ~/.bashrc:)");
        let _ = writeln!(err, "  source <({bin} completions bash)\n");
        let _ = writeln!(err, "### To make an alias (eg. 'h'), add this too:");
        let _ = writeln!(err, "  alias h={bin}");
        let _ = writeln!(err, "  complete -F _{bin} -o bashdefault -o default h\n");
        let _ = writeln!(
            err,
            "### If you don't use Bash, you can also use Fish or Zsh:"
        );
        let _ = writeln!(err, "### Fish (put this in ~/.config/fish/config.fish");
        let _ = writeln!(err, "  {bin} completions fish | source)\n");
        let _ = writeln!(err, "### Zsh (put this in ~/.zshrc)");
        let _ = writeln!(
            err,
            "  autoload -U compinit; compinit; source <({bin} completions zsh)"
        );

        1
    }
}

fn generate_completion_script<W: Write>(shell: Shell, out: &mut W) {
    clap_complete::generate(shell, &mut cli::app(), env!("CARGO_BIN_NAME"), out)
}

#[test]
fn run_once_hello_custom_name() {
    let mut out = Vec::new();
    let mut err = Vec::new();

    let code = crate::run_cli(["test-bin", "hello", "Ryan"], &mut out, &mut err);

    assert_eq!(code, 0);
    assert!(String::from_utf8(out).unwrap().contains("Hello, Ryan!"));
    assert!(err.is_empty());
}
