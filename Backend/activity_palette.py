"""Стабильная палитра цветов для популярных приложений + детерминированный fallback."""
import hashlib

KNOWN_APPS = {
    "visual studio code": ("Visual Studio Code", "#007ACC"),
    "code":               ("Visual Studio Code", "#007ACC"),
    "vscode":             ("Visual Studio Code", "#007ACC"),
    "telegram":           ("Telegram",            "#2DA5E1"),
    "slack":              ("Slack",               "#4A154B"),
    "figma":              ("Figma",               "#F24E1E"),
    "google meet":        ("Google Meet",         "#00AC47"),
    "meet":               ("Google Meet",         "#00AC47"),
    "zoom":               ("Zoom",                "#2D8CFF"),
    "chrome":             ("Google Chrome",       "#4285F4"),
    "firefox":            ("Firefox",             "#FF7139"),
    "edge":               ("Microsoft Edge",      "#0078D7"),
    "notion":             ("Notion",              "#000000"),
    "jira":               ("Jira",                "#0052CC"),
    "github":             ("GitHub",              "#181717"),
    "youtrack":           ("YouTrack",            "#9333EA"),
    "outlook":            ("Outlook",             "#0078D4"),
    "gmail":              ("Gmail",               "#EA4335"),
    "spotify":            ("Spotify",             "#1DB954"),
    "discord":            ("Discord",             "#5865F2"),
    "terminal":           ("Terminal",            "#111827"),
    "powershell":         ("PowerShell",          "#012456"),
    "cmd":                ("CMD",                 "#1F2937"),
    "kiro":               ("Kiro",                "#6366F1"),
}

FALLBACK_COLORS = [
    "#6366F1", "#EC4899", "#F59E0B", "#10B981", "#8B5CF6",
    "#0EA5E9", "#EF4444", "#14B8A6", "#F472B6", "#22C55E",
]


def normalize(app_name: str) -> tuple[str, str]:
    """Возвращает (display_name, hex_color) для приложения."""
    raw = (app_name or "").strip()
    key = raw.lower()

    for token, (display, color) in KNOWN_APPS.items():
        if token in key:
            return display, color

    # Стабильный цвет на основе хеша
    digest = hashlib.md5(raw.encode("utf-8")).digest() if raw else b"\x00"
    color = FALLBACK_COLORS[digest[0] % len(FALLBACK_COLORS)]
    display = raw if raw else "Прочее"
    return display, color


def format_minutes(minutes: int) -> str:
    """1ч 30м, 45м, 5с — компактный формат для UI."""
    if minutes <= 0:
        return "0м"
    hours = minutes // 60
    mins = minutes % 60
    if hours and mins:
        return f"{hours}ч {mins}м"
    if hours:
        return f"{hours}ч"
    return f"{mins}м"
