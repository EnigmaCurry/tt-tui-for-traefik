# tt-tui-for-traefik

`tt` is a console TUI dashboard for
[Traefik](https://doc.traefik.io/traefik/).

<img
src="https://github.com/EnigmaCurry/tt-tui-for-traefik/blob/master/_img/TraefikTUI_2026-01-19T21_29_23_594691.svg">

This program is a third party companion tool for Traefik. Traefik is a
trademark of [Traefik Labs](https://traefik.io/).


## Install

 * Install [uv](https://docs.astral.sh/uv/#installation)

```
uv tool install tt-tui-for-traefik
```

 * Make sure your PATH environment variable (e.g., in `~/.bashrc`)
   includes the directory `${HOME}/.local/bin`.

## Usage

The `tt` tool is installed at `${HOME}/.local/bin/tt`.

```
usage: tt [-h] [--link LINK] [--url URL] [--username USERNAME] [--password PASSWORD]

`tt` is a console TUI dashboard for Traefik

options:
  -h, --help           show this help message and exit
  --link, -l LINK      Deep link to a resource (e.g., entrypoint#websecure, middleware#mtls@file,
                       router:tcp#myrouter)
  --url, -u URL        Direct connection URL (disables Settings tab)
  --username USERNAME  HTTP basic auth username (requires --url)
  --password PASSWORD  HTTP basic auth password (requires --url)
```

### Keyboard navigation

 * Press `Tab` to cycle through the panels that can be focussed.
 * Use the arrow keys to select elements in the focussed pane.
 * Press `Enter` to descend the focus into the selected tab.
 * Press `ESC` to ascend the focus back to the tab bar.
 * Press `q` to quit.
 * Press `/` to search.
 * Press `Ctrl` + `P` to bring up the Pallete. 
   * Select the `Keys` command to show a help screen with all of the
     contextual keybindings.
   * Select the `Theme` command to change the inteface theme.

### Mouse navigation

In modern terminals, mouse / pointer support is enabled by default.
You can click on tabs and buttons in the terminal window to navigate
the app.

### Configure Traefik API

The connection information must be set one of two ways:

 * On the `Settings` tab, enter the URL with port, username, and passsword.
 * Via the `--url`, `--username` and `--password` command line options
   (this disables the `Settings` tab for this session).

All settings are saved to the file
`${HOME}/.local/share/tt-tui-for-traefik/config.toml`. *WARNING: This
config file includes Traefik API credetials!*

## Development

Put this in `~/.bashrc` to create a `tt` alias for development purposes:

```
alias tt="uv --project ${HOME}/git/vendor/enigmacurry/tt-tui-for-traefik run tt
```
