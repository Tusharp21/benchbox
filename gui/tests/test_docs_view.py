from __future__ import annotations

from pytestqt.qtbot import QtBot

from benchbox_gui.views.docs_view import COMMAND_CATALOGUE, DocumentationView


def test_docs_view_starts_with_every_card_visible(qtbot: QtBot) -> None:
    view = DocumentationView()
    qtbot.addWidget(view)
    visible = [c for c in view._cards if not c.isHidden()]  # noqa: SLF001
    assert len(visible) == len(COMMAND_CATALOGUE)


def test_docs_view_search_filters_cards_in_place(qtbot: QtBot) -> None:
    view = DocumentationView()
    qtbot.addWidget(view)
    # Pre-filter: at least a handful of cards exist for the 'backup' word.
    view._search.setText("backup")  # noqa: SLF001
    visible = [c for c in view._cards if not c.isHidden()]  # noqa: SLF001
    assert 0 < len(visible) < len(COMMAND_CATALOGUE)
    for card in visible:
        blob = (
            card.entry.title + card.entry.example + card.entry.description + card.entry.category
        ).lower()
        assert "backup" in blob


def test_docs_view_multi_term_search_is_and(qtbot: QtBot) -> None:
    # Every whitespace-separated term must match — "site backup" only keeps
    # rows that mention both, not either.
    view = DocumentationView()
    qtbot.addWidget(view)
    view._search.setText("site backup")  # noqa: SLF001
    visible = [c for c in view._cards if not c.isHidden()]  # noqa: SLF001
    assert all(
        "site" in (c.entry.title + c.entry.example + c.entry.description).lower()
        and "backup" in (c.entry.title + c.entry.example + c.entry.description).lower()
        for c in visible
    )


def test_docs_view_empty_state_shows_when_no_match(qtbot: QtBot) -> None:
    view = DocumentationView()
    qtbot.addWidget(view)
    view._search.setText("zzzzzzzz-no-such-command")  # noqa: SLF001
    assert view._no_results.isHidden() is False  # noqa: SLF001
    assert all(c.isHidden() for c in view._cards)  # noqa: SLF001


def test_command_catalogue_categories_are_non_empty() -> None:
    # Sanity — every entry carries the four required fields.
    for entry in COMMAND_CATALOGUE:
        assert entry.title.strip()
        assert entry.example.strip()
        assert entry.description.strip()
        assert entry.category.strip()
