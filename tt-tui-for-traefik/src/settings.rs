use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    env, fs, io,
    path::{Path, PathBuf},
};
use url::Url;

pub const APP_DIR: &str = "tt-tui-for-traefik";
pub const CONFIG_FILE: &str = "config.toml";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectionStatus {
    Disconnected,
    Connected,
}

impl Default for ConnectionStatus {
    fn default() -> Self {
        Self::Disconnected
    }
}

/// Runtime-only info (not saved to disk).
#[derive(Debug, Clone, Default)]
pub struct ProfileRuntime {
    pub status: ConnectionStatus,
    pub version: Option<String>,
}

/// Persisted config root.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    /// A schema version for future migrations.
    #[serde(default)]
    pub schema_version: u32,

    /// The currently selected profile name.
    #[serde(default)]
    pub selected_profile: Option<String>,

    #[serde(default)]
    pub selected_tab: Option<String>,

    /// Profiles keyed by profile name.
    #[serde(default)]
    pub profiles: BTreeMap<String, Profile>,

    /// Runtime-only data keyed by profile name.
    #[serde(skip)]
    pub runtime: BTreeMap<String, ProfileRuntime>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Profile {
    #[serde(default = "default_url")]
    pub url: String,

    /// Basic auth (optional).
    #[serde(default)]
    pub basic_auth: Option<BasicAuth>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BasicAuth {
    #[serde(default)]
    pub username: String,

    #[serde(default)]
    pub password: String,
}

fn default_url() -> String {
    "http://localhost:8080".to_string()
}

impl Default for Settings {
    fn default() -> Self {
        let mut s = Self {
            schema_version: 1,
            selected_profile: None,
            profiles: BTreeMap::new(),
            selected_tab: Some("Settings".to_string()),
            runtime: BTreeMap::new(),
        };

        let url = default_url();
        let key =
            Settings::profile_key_from_url(&url).unwrap_or_else(|| "localhost:8080".to_string());

        s.profiles.insert(
            key.clone(),
            Profile {
                url,
                ..Profile::default()
            },
        );
        s.selected_profile = Some(key);

        s
    }
}

impl Default for Profile {
    fn default() -> Self {
        Self {
            url: default_url(),
            basic_auth: None,
        }
    }
}

#[derive(Debug)]
pub enum SettingsError {
    Io(io::Error),
    TomlDe(toml::de::Error),
    TomlSer(toml::ser::Error),
    NoHomeDir,
}

impl std::fmt::Display for SettingsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SettingsError::Io(e) => write!(f, "io error: {e}"),
            SettingsError::TomlDe(e) => write!(f, "toml decode error: {e}"),
            SettingsError::TomlSer(e) => write!(f, "toml encode error: {e}"),
            SettingsError::NoHomeDir => write!(f, "unable to determine home directory"),
        }
    }
}

impl std::error::Error for SettingsError {}

impl From<io::Error> for SettingsError {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}

impl From<toml::de::Error> for SettingsError {
    fn from(e: toml::de::Error) -> Self {
        Self::TomlDe(e)
    }
}

impl From<toml::ser::Error> for SettingsError {
    fn from(e: toml::ser::Error) -> Self {
        Self::TomlSer(e)
    }
}

impl Settings {
    /// Compute config path in a "local" XDG-ish directory.
    ///
    /// Preference order:
    /// - $TT_LOCAL_HOME/tt-tui-for-traefik/config.toml
    /// - $XDG_DATA_HOME/tt-tui-for-traefik/config.toml
    /// - ~/.local/share/tt-tui-for-traefik/config.toml   (matches your example)
    pub fn path() -> Result<PathBuf, SettingsError> {
        if let Ok(base) = env::var("TT_LOCAL_HOME") {
            return Ok(PathBuf::from(base).join(APP_DIR).join(CONFIG_FILE));
        }

        if let Ok(base) = env::var("XDG_DATA_HOME") {
            return Ok(PathBuf::from(base).join(APP_DIR).join(CONFIG_FILE));
        }

        let home = dirs::home_dir().ok_or(SettingsError::NoHomeDir)?;
        Ok(home
            .join(".local")
            .join("share")
            .join(APP_DIR)
            .join(CONFIG_FILE))
    }

    pub fn load_or_default() -> Result<Self, SettingsError> {
        let path = Self::path()?;
        if path.exists() {
            Self::load(&path)
        } else {
            Ok(Self::default())
        }
    }

    pub fn load(path: &Path) -> Result<Self, SettingsError> {
        let txt = fs::read_to_string(path)?;
        let mut s: Settings = toml::from_str(&txt)?;
        s.ensure_runtime();
        s.ensure_selected_profile();
        Ok(s)
    }

    pub fn save(&self) -> Result<(), SettingsError> {
        let path = Self::path()?;
        self.save_to(&path)
    }

    pub fn save_to(&self, path: &Path) -> Result<(), SettingsError> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        // Atomic-ish write: write temp then rename.
        let tmp = path.with_extension("toml.tmp");
        let data = toml::to_string_pretty(&self)?;
        fs::write(&tmp, data)?;
        fs::rename(&tmp, path)?;
        Ok(())
    }

    pub fn selected_name(&self) -> Option<&str> {
        self.selected_profile.as_deref()
    }

    pub fn selected_profile(&self) -> Option<&Profile> {
        self.selected_name().and_then(|n| self.profiles.get(n))
    }

    pub fn selected_profile_mut(&mut self) -> Option<&mut Profile> {
        let name = self.selected_profile.clone()?;
        self.profiles.get_mut(&name)
    }

    pub fn set_selected(&mut self, name: &str) {
        if self.profiles.contains_key(name) {
            self.selected_profile = Some(name.to_string());
        }
    }

    pub fn add_profile(&mut self, name: &str) -> String {
        let base = Self::profile_key_from_url(name).unwrap_or_else(|| "profile".to_string());
        let name = self.unique_profile_name(&base, None);
        self.profiles.insert(
            name.clone(),
            Profile {
                url: "".to_string(),
                ..Profile::default()
            },
        );
        self.runtime.insert(name.clone(), ProfileRuntime::default());
        self.selected_profile = Some(name.clone());
        name
    }

    pub fn remove_profile(&mut self, name: &str) -> bool {
        let existed = self.profiles.remove(name).is_some();
        self.runtime.remove(name);

        if existed {
            if self.selected_name() == Some(name) {
                self.selected_profile = self.profiles.keys().next().cloned();
            }
        }

        existed
    }

    pub fn runtime_for(&self, name: &str) -> ProfileRuntime {
        self.runtime.get(name).cloned().unwrap_or_default()
    }

    pub fn runtime_for_mut(&mut self, name: &str) -> &mut ProfileRuntime {
        self.runtime.entry(name.to_string()).or_default()
    }

    fn ensure_runtime(&mut self) {
        // Ensure runtime map has entries for all persisted profiles.
        for name in self.profiles.keys().cloned().collect::<Vec<_>>() {
            self.runtime.entry(name).or_default();
        }
    }

    fn ensure_selected_profile(&mut self) {
        // If selected profile missing, pick the first available.
        if let Some(sel) = self.selected_profile.clone() {
            if self.profiles.contains_key(&sel) {
                return;
            }
        }
        self.selected_profile = self.profiles.keys().next().cloned();
    }

    /// Turn a URL into a canonical profile key: "host:port" (or "host" if no port).
    /// Accepts URLs missing a scheme by assuming http://.
    pub fn profile_key_from_url(raw: &str) -> Option<String> {
        let raw = raw.trim();
        if raw.is_empty() {
            return None;
        }

        let parsed = Url::parse(raw)
            .or_else(|_| Url::parse(&format!("http://{raw}")))
            .ok()?;

        let host = parsed.host_str()?.to_string();
        let key = match parsed.port() {
            Some(p) => format!("{host}:{p}"),
            None => host,
        };

        Some(key)
    }

    fn unique_profile_name(&self, base: &str, old: Option<&str>) -> String {
        // If the base is either unused, or it's the old name we're renaming from, keep it.
        if !self.profiles.contains_key(base) || old == Some(base) {
            return base.to_string();
        }

        let mut i = 2u32;
        loop {
            let candidate = format!("{base}-{i}");
            if !self.profiles.contains_key(&candidate) {
                return candidate;
            }
            i += 1;
        }
    }

    /// Rename a profile key (moving persisted + runtime data), updating selection.
    /// Returns the final key used (may get "-2" suffix if needed).
    pub fn rename_profile(&mut self, old: &str, new_base: &str) -> Option<String> {
        if !self.profiles.contains_key(old) {
            return None;
        }

        let final_name = self.unique_profile_name(new_base, Some(old));

        // If rename is a no-op after uniqueness resolution, we still "succeed".
        if final_name == old {
            return Some(old.to_string());
        }

        let profile = self.profiles.remove(old)?;
        self.profiles.insert(final_name.clone(), profile);

        let rt = self.runtime.remove(old).unwrap_or_default();
        self.runtime.insert(final_name.clone(), rt);

        if self.selected_profile.as_deref() == Some(old) {
            self.selected_profile = Some(final_name.clone());
        }

        Some(final_name)
    }

    pub fn selected_tab_name(&self) -> &str {
        self.selected_tab.as_deref().unwrap_or("Settings")
    }

    pub fn set_selected_tab_name(&mut self, tab: &str) {
        self.selected_tab = Some(tab.to_string());
        // Match whatever behavior you use for selected profile persistence:
        let _ = self.save();
    }
}
