# tt-tui-for-traefik

[![Crates.io](https://img.shields.io/crates/v/tt-tui-for-traefik?color=blue
)](https://crates.io/crates/tt-tui-for-traefik)
[![Coverage](https://img.shields.io/badge/Coverage-Report-purple)](https://enigmacurry.github.io/tt-tui-for-traefik/coverage/master/)


## Install

[Download the latest release for your platform.](https://github.com/enigmacurry/tt-tui-for-traefik/releases)

Or install via cargo ([crates.io/crates/tt-tui-for-traefik](https://crates.io/crates/tt-tui-for-traefik)):

```
cargo install tt-tui-for-traefik
```

### Tab completion

To install tab completion support, put this in your `~/.bashrc` (assuming you use Bash):

```
### Bash completion for tt-tui-for-traefik (Put this in ~/.bashrc)
source <(tt-tui-for-traefik completions bash)
```

If you don't like to type out the full name `tt-tui-for-traefik`, you can make
a shorter alias (`h`), as well as enable tab completion for the alias
(`h`):

```
### Alias tt-tui-for-traefik as tt (Put this in ~/.bashrc):
alias tt=tt-tui-for-traefik
complete -F _tt-tui-for-traefik -o bashdefault -o default tt
```

Completion for Zsh and/or Fish has also been implemented, but the
author has not tested this:

```
### Zsh completion for tt-tui-for-traefik (Put this in ~/.zshrc):
autoload -U compinit; compinit; source <(tt-tui-for-traefik completions zsh)

### Fish completion for tt-tui-for-traefik (Put this in ~/.config/fish/config.fish):
tt-tui-for-traefik completions fish | source
```

## Usage

```
$ tt-tui-for-traefik

Usage: tt-tui-for-traefik [OPTIONS] [COMMAND]

Commands:
  hello        Greeting
  completions  Generates shell completions script (tab completion)
  help         Print this message or the help of the given subcommand(s)

Options:
      --log <LEVEL>  Sets the log level, overriding the RUST_LOG environment variable. [possible values: trace, debug, info, warn, error]
  -v                 Sets the log level to debug.
  -h, --help         Print help
  -V, --version      Print version
```

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md)
