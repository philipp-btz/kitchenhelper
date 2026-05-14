# Menu Editor Rework — Design Spec

**Date:** 2026-05-14
**Branch:** remake/cleanroom (`.worktrees/remake/`)

## Overview

Rework the menu item editor to remove prices, give each extra its own text field, and add drag-and-drop reordering for both items and extras — with a responsive layout that works well on mobile.

## What Changes

| File | Change |
|------|--------|
| `menu.py` | Remove `price` from `normalize_item` |
| `templates/menu_editor.html` | Full rewrite of layout and JS |

No backend route changes. No data migration.

## Data Model

`price` is removed from the item schema. Existing menu JSON files that still contain `price` will load and re-save without it (silently dropped by `normalize_item`).

Item shape after change:
```json
{
  "name": "Burger",
  "printer": "1",
  "bg_color": "#ffe0b2",
  "extras": ["ohne Zwiebeln", "extra Käse"]
}
```

## Layout

### Wide screen (≥ 640px) — Option C

Each item is a card with:
- One row: drag handle `⠿` | name input | printer select | color picker | delete button
- `<details>` below (indented, collapsed by default, summary shows extra count):
  - SortableJS-managed extras list — each row: drag handle, text input, remove button
  - `+ Extra` button

### Narrow screen (< 640px) — Option B

Same item card, but:
- Header row: drag handle | item name label | delete button
- Two-column grid below: left = name/printer/color stacked; right = extras list (always visible, no `<details>` toggle)
- Extras drag handles retained on mobile

Breakpoint is `640px`, implemented with a CSS `@media (max-width: 639px)` block.

## Drag and Drop

**Library:** SortableJS, loaded from CDN (`cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js`).

Two Sortable instances per item card:
- One on `#items-container` for reordering items (handle: `.item-drag-handle`)
- One on each `.extras-list` for reordering extras within an item (handle: `.extra-drag-handle`)

When `+ Item` adds a new card, a new Sortable instance is created for its extras list.

## Submit Handler

On form submit, JS walks `#items-container` in DOM order, collecting:
- `.field-name` value
- `.field-printer` value
- `.field-bg` value
- All `.field-extra` values (filtered empty, in DOM order)

Result serialized as JSON into hidden `items_json` field.

## SortableJS CDN

```html
<script src="https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js"></script>
```

Loaded in `{% block head %}`. If CDN is unavailable the editor still works for add/remove/edit — drag reorder silently fails.
