"""Searchable command reference."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class CommandEntry:
    title: str
    example: str
    description: str
    category: str


# Grouped roughly by what the user is *trying* to do, not by which bench
# sub-command they happen to touch. Keep examples copy-pasteable — real
# paths or placeholder names (no ``<...>`` angle brackets in the argv).
COMMAND_CATALOGUE: tuple[CommandEntry, ...] = (
    # ---------- Bench lifecycle ----------
    CommandEntry(
        category="Bench lifecycle",
        title="Create a new bench",
        example="bench init frappe-bench --frappe-branch version-15 --python python3",
        description="Scaffolds a new bench directory with Frappe cloned at the given "
        "branch and a fresh Python virtualenv.",
    ),
    CommandEntry(
        category="Bench lifecycle",
        title="Start the bench (dev processes)",
        example="bench start",
        description="Runs honcho with Frappe's Procfile — web worker, schedulers, "
        "socketio, Redis. Ctrl-C stops them cleanly.",
    ),
    CommandEntry(
        category="Bench lifecycle",
        title="Switch the Frappe branch on an existing bench",
        example="bench switch-to-branch version-15 frappe erpnext --upgrade",
        description="Pulls each listed app onto the named branch and rebuilds.",
    ),
    CommandEntry(
        category="Bench lifecycle",
        title="Update a bench (pull + migrate + build)",
        example="bench update",
        description="Pulls every app, upgrades pip requirements, runs migrations "
        "on every site, rebuilds assets.",
    ),
    CommandEntry(
        category="Bench lifecycle",
        title="Rebuild front-end assets only",
        example="bench build",
        description="Skips DB/migration work — just rebuilds CSS/JS bundles. "
        "Add ``--app erpnext`` to narrow.",
    ),
    CommandEntry(
        category="Bench lifecycle",
        title="Pin Node / npm for this bench",
        example="nvm use 18",
        description="benchbox provisions Node via nvm; run this from the bench "
        "directory to use the installed major on your shell.",
    ),
    # ---------- Sites ----------
    CommandEntry(
        category="Sites",
        title="Create a new site",
        example="bench new-site site1.local --db-root-password root-pw --admin-password admin",
        description="Bootstraps a site in ``sites/site1.local/`` with its own "
        "MariaDB database and an Administrator user.",
    ),
    CommandEntry(
        category="Sites",
        title="Drop a site",
        example="bench drop-site site1.local --db-root-password root-pw",
        description="Permanently removes the site's DB + files. Add "
        "``--no-backup`` to skip the pre-drop backup.",
    ),
    CommandEntry(
        category="Sites",
        title="Set a site as the default",
        example="bench use site1.local",
        description="Writes ``currentsite.txt`` so ``bench --site`` isn't needed "
        "for subsequent commands.",
    ),
    CommandEntry(
        category="Sites",
        title="Enable developer mode on a site",
        example="bench --site site1.local set-config developer_mode 1",
        description="Turns on hot-reload + un-minified assets + verbose errors.",
    ),
    CommandEntry(
        category="Sites",
        title="Reset the Administrator password",
        example="bench --site site1.local set-admin-password new-password",
        description="One-shot password reset. Works even if you've lost the "
        "existing admin credentials.",
    ),
    CommandEntry(
        category="Sites",
        title="Run migrations on a single site",
        example="bench --site site1.local migrate",
        description="Re-applies every unapplied patch / schema change. Typical "
        "after an app upgrade.",
    ),
    CommandEntry(
        category="Sites",
        title="Migrate every site on the bench",
        example="bench migrate",
        description="Runs the migrate command for every site sequentially.",
    ),
    # ---------- Apps ----------
    CommandEntry(
        category="Apps",
        title="Clone a Frappe app into the bench",
        example="bench get-app https://github.com/frappe/erpnext --branch version-15",
        description="Clones the repo into ``apps/`` and pip-installs it into the "
        "bench's venv. Does NOT install onto any site yet.",
    ),
    CommandEntry(
        category="Apps",
        title="Install an app onto a site",
        example="bench --site site1.local install-app erpnext",
        description="Runs the app's DocType setup + fixtures on that specific "
        "site. Needed after ``get-app`` before the app is usable.",
    ),
    CommandEntry(
        category="Apps",
        title="Uninstall an app from a site",
        example="bench --site site1.local uninstall-app erpnext --yes",
        description="Drops the app's DocTypes from one site but keeps the code "
        "in ``apps/``. ``--yes`` skips the interactive prompt.",
    ),
    CommandEntry(
        category="Apps",
        title="Remove an app from the bench entirely",
        example="bench remove-app erpnext",
        description="Deletes ``apps/erpnext/`` after verifying no site still has "
        "it installed. Add ``--force`` to skip the check.",
    ),
    CommandEntry(
        category="Apps",
        title="Fetch a private GitHub app with a token",
        example="bench get-app https://TOKEN@github.com/acme/private-app.git --branch main",
        description="Personal access token in the URL's userinfo is how bench "
        "authenticates against private HTTPS remotes.",
    ),
    # ---------- Backup & restore ----------
    CommandEntry(
        category="Backup & restore",
        title="Back up a site (DB only)",
        example="bench --site site1.local backup",
        description="Dumps the DB to ``sites/site1.local/private/backups/`` with "
        "a timestamped filename.",
    ),
    CommandEntry(
        category="Backup & restore",
        title="Back up a site with files",
        example="bench --site site1.local backup --with-files",
        description="Also tars the site's public + private file directories "
        "alongside the DB dump.",
    ),
    CommandEntry(
        category="Backup & restore",
        title="Restore a site from a SQL backup",
        example="bench --site site1.local restore /path/to/backup.sql.gz "
        "--db-root-password root-pw",
        description="Overwrites the site's DB with the dump. Add "
        "``--with-public-files`` / ``--with-private-files`` to restore files too.",
    ),
    CommandEntry(
        category="Backup & restore",
        title="Restore with file archives",
        example="bench --site site1.local restore backup.sql.gz "
        "--with-public-files files.tar --with-private-files private-files.tar "
        "--db-root-password root-pw",
        description="Full restore — DB + both file trees — as produced by "
        "``backup --with-files``.",
    ),
    # ---------- Schedulers & workers ----------
    CommandEntry(
        category="Schedulers & workers",
        title="Enable the scheduler on a site",
        example="bench --site site1.local enable-scheduler",
        description="Scheduled events / email digests / auto-repeat won't fire "
        "until this is on.",
    ),
    CommandEntry(
        category="Schedulers & workers",
        title="Run pending scheduled events manually",
        example="bench --site site1.local execute frappe.utils.scheduler.enqueue_events "
        "--kwargs \"{'site':'site1.local'}\"",
        description="Useful in dev to avoid waiting for the cron tick.",
    ),
    CommandEntry(
        category="Schedulers & workers",
        title="Watch the background-worker queue",
        example="bench --site site1.local worker --queue default",
        description="Runs a worker that drains the Redis Queue until you Ctrl-C.",
    ),
    # ---------- Diagnostics ----------
    CommandEntry(
        category="Diagnostics",
        title="Open a Python shell with Frappe loaded",
        example="bench --site site1.local console",
        description="IPython-style REPL with ``frappe`` and the site context "
        "already imported. Great for ad-hoc queries.",
    ),
    CommandEntry(
        category="Diagnostics",
        title="Run a DocType query from the shell",
        example="bench --site site1.local execute frappe.get_all --args \"['User']\"",
        description="One-shot equivalent of the console — prints the return "
        "value and exits.",
    ),
    CommandEntry(
        category="Diagnostics",
        title="Check the bench version",
        example="bench version",
        description="Prints Frappe + every installed app's version string and "
        "git branch. First thing to paste into a bug report.",
    ),
    CommandEntry(
        category="Diagnostics",
        title="Show the bench's Procfile graph",
        example="bench src",
        description="Dumps the running-process tree so you can see what "
        "``bench start`` will spawn.",
    ),
    # ---------- benchbox ----------
    CommandEntry(
        category="benchbox",
        title="Install base system dependencies",
        example="benchbox install --yes",
        description="Runs the apt/python/mariadb/redis/node/wkhtmltopdf/bench "
        "components in order. First thing to run on a fresh Ubuntu machine.",
    ),
    CommandEntry(
        category="benchbox",
        title="Preview what would be installed",
        example="benchbox install --dry-run",
        description="Same planner, but never executes anything. Useful to see "
        "what steps will run on an existing setup.",
    ),
    CommandEntry(
        category="benchbox",
        title="List discovered benches",
        example="benchbox list",
        description="Walks ``$HOME`` and prints every directory that looks like "
        "a Frappe bench (the same scan the GUI runs).",
    ),
    CommandEntry(
        category="benchbox",
        title="Print a bench's introspection",
        example="benchbox info ~/frappe-bench",
        description="Dumps Frappe version, Python, Node, git branch, sites, "
        "installed apps — the same data the GUI's bench-detail pane shows.",
    ),
)


class _CommandCard(QFrame):

    def __init__(self, entry: CommandEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._entry = entry

        title = QLabel(entry.title)
        title.setProperty("role", "h2")

        category = QLabel(entry.category)
        category.setProperty("role", "badge")

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(title, 1)
        header.addWidget(category, 0, Qt.AlignmentFlag.AlignTop)

        self._example = QLabel(entry.example)
        self._example.setWordWrap(True)
        self._example.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 10)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._example.setFont(mono)
        self._example.setProperty("role", "code")
        self._example.setStyleSheet(
            "padding: 8px 12px; border-radius: 6px; "
            "background-color: rgba(128,128,160,0.12);"
        )

        description = QLabel(entry.description)
        description.setWordWrap(True)
        description.setProperty("role", "dim")

        copy = QPushButton("Copy")
        copy.setProperty("role", "ghost")
        copy.setCursor(Qt.CursorShape.PointingHandCursor)
        copy.setFixedWidth(72)
        copy.clicked.connect(self._copy_to_clipboard)

        self._copied_hint = QLabel("")
        self._copied_hint.setProperty("role", "dim")

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        actions.addWidget(self._copied_hint)
        actions.addWidget(copy)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        root.addLayout(header)
        root.addWidget(self._example)
        root.addWidget(description)
        root.addLayout(actions)

    @property
    def entry(self) -> CommandEntry:
        return self._entry

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        haystack = (
            f"{self._entry.title} {self._entry.example} "
            f"{self._entry.description} {self._entry.category}"
        ).lower()
        # Every whitespace-separated term must be present — lets the user
        # narrow by typing "site backup" and getting only sites+backup rows.
        return all(term in haystack for term in needle.lower().split())

    def _copy_to_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._entry.example)
            self._copied_hint.setText("copied")


class DocumentationView(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("Documentation")
        title.setProperty("role", "h1")
        subtitle = QLabel(
            f"{len(COMMAND_CATALOGUE)} common bench & benchbox commands — "
            "search by any word, then click Copy to drop the example into your clipboard"
        )
        subtitle.setProperty("role", "dim")
        subtitle.setWordWrap(True)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        filter_label = QLabel("Search:")
        filter_label.setProperty("role", "dim")

        self._search = QLineEdit()
        self._search.setPlaceholderText("e.g. backup, new-site, get-app, migrate…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search_changed)

        self._count_label = QLabel()
        self._count_label.setProperty("role", "dim")

        filter_bar = QFrame()
        filter_bar.setObjectName("FilterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(12)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self._search, 1)
        filter_layout.addWidget(self._count_label)

        # Cards stacked vertically, grouped by category. We build one card
        # per entry and one section label per category, then filter them
        # in-place on search (cheaper than rebuilding the widget tree).
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(10)

        self._cards: list[_CommandCard] = []
        self._section_labels: dict[str, QLabel] = {}
        for category in _unique_categories():
            section = QLabel(category)
            section.setProperty("role", "h2")
            section.setContentsMargins(4, 12, 0, 2)
            content_layout.addWidget(section)
            self._section_labels[category] = section
            for entry in COMMAND_CATALOGUE:
                if entry.category != category:
                    continue
                card = _CommandCard(entry)
                content_layout.addWidget(card)
                self._cards.append(card)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        self._no_results = QLabel("No commands match your search.")
        self._no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results.setProperty("role", "dim")
        self._no_results.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addLayout(header_text)
        root.addWidget(filter_bar)
        root.addWidget(self._no_results)
        root.addWidget(scroll, 1)

        self._update_count(len(self._cards))

    # --- filter --------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        needle = text.strip()
        visible = 0
        visible_categories: set[str] = set()
        for card in self._cards:
            shown = card.matches(needle)
            card.setVisible(shown)
            if shown:
                visible += 1
                visible_categories.add(card.entry.category)
        # Hide section headings whose every card is filtered out.
        for category, label in self._section_labels.items():
            label.setVisible(category in visible_categories)

        self._update_count(visible)
        self._no_results.setVisible(visible == 0)

    def _update_count(self, visible: int) -> None:
        total = len(self._cards)
        if visible == total:
            self._count_label.setText(f"{total} commands")
        else:
            self._count_label.setText(f"{visible} / {total} matches")


def _unique_categories() -> list[str]:
    seen: list[str] = []
    for entry in COMMAND_CATALOGUE:
        if entry.category not in seen:
            seen.append(entry.category)
    return seen
