# tt-tui-for-traefik

A TUI dashboard for Traefik.

## Install

 * Install [uv](https://docs.astral.sh/uv/#installation)

```
uv tool install git+https://github.com/EnigmaCurry/tt-tui-for-traefik
```


## Usage

The tool is intalled as the binary `tt`.

```
usage: tt [-h] [--link LINK] [--url URL] [--username USERNAME] [--password PASSWORD]

TT TUI for Traefik

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

### Configure Traefik API

The connection information must be set one of two ways:

 * On the `Settings` tab, enter the URL with port, username, and passsword.
 * Via the `--url`, `--username` and `--password` command line options
   (this disables the `Settings` tab for this session).
