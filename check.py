"""
WKO Volontariat – Überwachung "Freie Plätze 2027"

Ruft die WKO-Seite ab, liest den Abschnitt "Bewerbung" bis "Freie Plätze 2027"
und vergleicht ihn mit dem letzten gespeicherten Stand (last_state.txt).
Bei einer Änderung kommt eine Push-Nachricht über ntfy aufs Handy.
"""
import json
import os
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

URL = "https://www.wko.at/aussenwirtschaft/volontariat"
STATE_FILE = Path("last_state.txt")
START_MARKER = "Bewerbung"  # Überschrift, ab der überwacht wird
END_MARKER = "Volontariatseinsatz in der EU Representation"  # hier endet der Abschnitt
NOT_FOUND = "ABSCHNITT NICHT GEFUNDEN"

BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "br", "tr", "section", "article",
              "h1", "h2", "h3", "h4", "h5", "h6"}


class TextExtractor(HTMLParser):
    """Macht aus HTML reinen Text, eine Zeile pro Absatz/Überschrift."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a" and not self.skip:
            href = dict(attrs).get("href")
            if href:
                self.parts.append(f" [Link: {href}] ")


    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def lines(self):
        text = "".join(self.parts)
        return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; wko-volontariat-check/1.0)",
        "Accept-Language": "de-AT,de;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_section(lines):
    if START_MARKER not in lines:
        return None
    start = lines.index(START_MARKER)
    end = next((i for i in range(start, len(lines)) if lines[i].startswith(END_MARKER)), len(lines))
    return "\n".join(lines[start:end])


def notify(title, message, priority=5):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        sys.exit("Fehler: Secret NTFY_TOPIC fehlt. Bitte in GitHub unter Settings > Secrets anlegen.")
    payload = {
        "topic": topic,
        "title": title,
        "message": message[:1500],
        "priority": priority,
        "click": URL,
        "tags": ["rotating_light"] if priority >= 4 else ["white_check_mark"],
    }
    req = urllib.request.Request(
        "https://ntfy.sh/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30)
    print(f"Push gesendet: {title}")


def main():
    parser = TextExtractor()
    parser.feed(fetch(URL))
    section = get_section(parser.lines())
    current = section if section else NOT_FOUND

    print("---- Überwachter Text ----")
    print(current)
    print("--------------------------")

    # Erster Lauf: Stand speichern und Test-Push schicken
    if not STATE_FILE.exists():
        notify("WKO-Check läuft",
               "Die Überwachung ist eingerichtet. Du bekommst eine Nachricht, "
               "sobald sich der Bewerbungs-Abschnitt ändert.",
               priority=3)
        STATE_FILE.write_text(current, encoding="utf-8")
        return

    old = STATE_FILE.read_text(encoding="utf-8")
    if current == old:
        print("Keine Änderung.")
        return

    if section is None:
        msg = ("Der Bewerbungs-Abschnitt wurde nicht mehr gefunden, "
               "die Seite wurde wohl umgebaut. Bitte selbst nachsehen!")
    else:
        old_lines = set(old.splitlines())
        new_lines = [line for line in current.splitlines() if line not in old_lines]
        if new_lines:
            msg = "Neu auf der Seite:\n" + "\n".join(new_lines)
        else:
            msg = "Text wurde entfernt oder umgestellt. Bitte nachsehen!"

    notify("WKO Volontariat: Seite geändert!", msg + "\n\nTippen zum Öffnen.")
    STATE_FILE.write_text(current, encoding="utf-8")


if __name__ == "__main__":
    main()
