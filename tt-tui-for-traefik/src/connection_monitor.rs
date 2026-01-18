use base64::Engine;
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use crate::settings::ConnectionStatus;

#[derive(Debug, Clone)]
pub struct MonitorTarget {
    pub name: String,
    pub base_url: String,
    pub username: Option<String>,
    pub password: Option<String>,
}

#[derive(Debug)]
pub enum MonitorCmd {
    SetTarget(Option<MonitorTarget>),
    Stop,
}

#[derive(Debug)]
pub enum MonitorEvent {
    Update {
        name: String,
        status: ConnectionStatus,
        version: Option<String>,
    },
}

fn build_version_url(base: &str) -> String {
    let base = base.trim_end_matches('/');
    format!("{base}/api/version")
}

fn extract_version(body: &str) -> Option<String> {
    // /api/version returns JSON. We’ll accept a few common keys.
    let v: serde_json::Value = serde_json::from_str(body).ok()?;
    v.get("Version")
        .or_else(|| v.get("version"))
        .or_else(|| v.get("tag"))
        .and_then(|x| x.as_str())
        .map(|s| s.to_string())
}

fn poll_version(t: &MonitorTarget) -> (ConnectionStatus, Option<String>) {
    let url = build_version_url(&t.base_url);

    let agent = ureq::Agent::new();
    let mut req = agent.get(&url).timeout(Duration::from_secs(2));

    // Basic auth (manual header)
    if let Some(user) = t.username.as_deref() {
        if !user.is_empty() {
            let pass = t.password.as_deref().unwrap_or("");
            let raw = format!("{user}:{pass}");
            let enc = base64::engine::general_purpose::STANDARD.encode(raw.as_bytes());
            req = req.set("Authorization", &format!("Basic {enc}"));
        }
    }

    match req.call() {
        Ok(resp) => {
            let body = resp.into_string().unwrap_or_default();
            let version = extract_version(&body);
            (ConnectionStatus::Connected, version)
        }
        Err(_) => (ConnectionStatus::Disconnected, None),
    }
}

pub fn spawn_monitor() -> (
    mpsc::Sender<MonitorCmd>,
    mpsc::Receiver<MonitorEvent>,
    thread::JoinHandle<()>,
) {
    let (cmd_tx, cmd_rx) = mpsc::channel::<MonitorCmd>();
    let (evt_tx, evt_rx) = mpsc::channel::<MonitorEvent>();

    let handle = thread::spawn(move || {
        let mut target: Option<MonitorTarget> = None;
        let mut next_poll = Instant::now();

        loop {
            if let Some(t) = target.clone() {
                if Instant::now() >= next_poll {
                    let (status, version) = poll_version(&t);
                    let _ = evt_tx.send(MonitorEvent::Update {
                        name: t.name.clone(),
                        status,
                        version,
                    });
                    next_poll = Instant::now() + Duration::from_secs(5);
                }
            }

            match cmd_rx.recv_timeout(Duration::from_millis(200)) {
                Ok(MonitorCmd::SetTarget(t)) => {
                    target = t;
                    next_poll = Instant::now(); // poll immediately on change
                }
                Ok(MonitorCmd::Stop) => break,
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
    });

    (cmd_tx, evt_rx, handle)
}
