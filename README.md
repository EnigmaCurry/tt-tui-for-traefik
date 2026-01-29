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
          [--ssh-host SSH_HOST] [--ssh-remote-host SSH_REMOTE_HOST] [--ssh-remote-port SSH_REMOTE_PORT]

`tt` is a console TUI dashboard for Traefik

options:
  -h, --help                        show this help message and exit
  --link, -l LINK                   Deep link to a resource (e.g., entrypoint#websecure,
                                    middleware#mtls@file, router:tcp#myrouter)
  --url, -u URL                     Direct connection URL (disables Settings tab)
  --username USERNAME               HTTP basic auth username (requires --url)
  --password PASSWORD               HTTP basic auth password (requires --url)
  --ssh-host SSH_HOST               SSH host from ~/.ssh/config for tunnel (requires --url)
  --ssh-remote-host SSH_REMOTE_HOST Remote host for tunnel (default: localhost)
  --ssh-remote-port SSH_REMOTE_PORT Remote port for tunnel (default: 8080)
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

 * On the `Settings` tab, enter the URL with port, username, and password.
 * Via the `--url`, `--username` and `--password` command line options
   (this disables the `Settings` tab for this session).

All settings are saved to the file
`${HOME}/.local/share/tt-tui-for-traefik/config.toml`. *WARNING: This
config file includes Traefik API credentials!*

### SSH Tunnel Support

`tt` can connect to remote Traefik instances via SSH tunnels. This is
useful when your Traefik API is only accessible from a server and not
exposed publicly.

#### Prerequisites

Configure your SSH connection in `~/.ssh/config`. For example:

```
Host myserver
    HostName server.example.com
    User admin
    IdentityFile ~/.ssh/id_ed25519
    Port 22
```

The SSH tunnel feature reads settings from your SSH config, including
`HostName`, `User`, `Port`, and `IdentityFile`.

#### Command Line Usage

Use the `--ssh-host` argument along with `--url` to connect via an SSH
tunnel:

```
tt --url http://localhost:8080 --ssh-host myserver
```

The `--url` should specify the address of Traefik *as seen from the
remote server*. The SSH tunnel will forward this connection through
`myserver`.

Additional SSH options:

| Option              | Default     | Description                              |
|---------------------|-------------|------------------------------------------|
| `--ssh-host`        | (required)  | SSH host name from `~/.ssh/config`       |
| `--ssh-remote-host` | `localhost` | Traefik host as seen from the SSH server |
| `--ssh-remote-port` | `8080`      | Traefik port as seen from the SSH server |

Example connecting to Traefik on a non-default port:

```
tt --url http://localhost:9090 --ssh-host myserver \
   --ssh-remote-host localhost --ssh-remote-port 9090
```

#### Manual Setup via Settings Tab

You can also configure SSH tunnels through the Settings tab UI:

1. Create or select a profile on the Settings tab
2. Enter the Traefik URL (as seen from the remote server, e.g.,
   `http://localhost:8080`)
3. Check the **Enable SSH tunnel** checkbox
4. Fill in the SSH settings:
   - **SSH Host**: The host name from your `~/.ssh/config` (e.g.,
     `myserver`)
   - **Remote Host**: The hostname where Traefik is running, as seen
     from the SSH server (default: `localhost`)
   - **Remote Port**: The port Traefik is listening on (default:
     `8080`)
   - **Local Port**: Leave empty for automatic port selection, or
     specify a fixed local port
5. The tunnel status will show "Tunnel: Open (port XXXXX)" when
   connected successfully

The SSH tunnel settings are saved with the profile and will
automatically reconnect when you select that profile.

## Development

Put this in `~/.bashrc` to create a `tt` alias for development purposes:

```
alias tt="uv --project ${HOME}/git/vendor/enigmacurry/tt-tui-for-traefik run tt
```
