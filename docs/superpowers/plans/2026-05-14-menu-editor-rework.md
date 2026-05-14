# Menu Editor Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove price from menu items, give each extra its own draggable text field, and make the editor responsive (collapsible extras on wide screens, two-column card on mobile).

**Architecture:** Two-file change. `menu.py` drops `price` from normalization. `templates/menu_editor.html` is fully rewritten with SortableJS for drag-and-drop, a CSS-Grid-based responsive layout: on wide (≥640px) a flex row per item with collapsible `<details>` extras (Option C); on mobile (<640px) the card becomes a CSS grid with a header row, left column for fields, and right column for extras (Option B). A single set of form fields per item — no duplication. CSS hides/shows the mobile header and the wide-only controls.

**Tech Stack:** FastAPI/Jinja2, SortableJS (CDN), vanilla JS, CSS Grid, CSS media query.

---

**Working directory for all commands:** `.worktrees/remake/`

**Run tests with:** `uv run pytest tests/ -q`

**Baseline:** 33 tests passing.

---

### Task 1: Remove price from menu.py

**Files:**
- Modify: `menu.py` — `normalize_item` function
- Modify: `tests/test_menu.py` — update assertions that check for `price`

- [ ] **Step 1: Update tests first**

Replace `tests/test_menu.py` entirely:

```python
import json
import pytest
import menu


def test_normalize_item_basic():
    raw = {"name": "Burger", "price": 9.5, "extras": ["Cheese"], "printer": "kitchen1"}
    result = menu.normalize_item(raw)
    assert result["name"] == "Burger"
    assert "price" not in result
    assert result["extras"] == ["Cheese"]
    assert result["printer"] == "kitchen1"
    assert result["bg_color"] == ""


def test_normalize_item_name_de_fallback():
    raw = {"name_de": "Schnitzel", "price": 12.0, "extras": [], "printer": "k"}
    result = menu.normalize_item(raw)
    assert result["name"] == "Schnitzel"


def test_normalize_item_strips_whitespace():
    raw = {"name": "  Pizza  ", "price": 8.0, "extras": [], "printer": " kitchen1 "}
    result = menu.normalize_item(raw)
    assert result["name"] == "Pizza"
    assert result["printer"] == "kitchen1"


def test_menu_path_safe(tmp_local):
    path = menu.menu_path("my_menu.json")
    assert path is not None
    assert "my_menu.json" in path
    assert ".." not in path


def test_menu_path_blocks_traversal(tmp_local):
    assert menu.menu_path("../../etc/passwd") is None


def test_list_menu_files(tmp_local):
    (tmp_local / "menus" / "alpha.json").write_text("[]")
    (tmp_local / "menus" / "beta.json").write_text("[]")
    files = menu.list_menu_files()
    assert "alpha.json" in files
    assert "beta.json" in files


def test_load_menu(tmp_local):
    data = [{"name": "Pizza", "price": 8.0, "extras": [], "printer": "k", "bg_color": ""}]
    (tmp_local / "menus" / "test.json").write_text(json.dumps(data))
    items = menu.load_menu(str(tmp_local / "menus" / "test.json"))
    assert len(items) == 1
    assert items[0]["name"] == "Pizza"
    assert "price" not in items[0]


def test_soft_delete_moves_file(tmp_local):
    (tmp_local / "menus" / "old.json").write_text("[]")
    menu.soft_delete("old.json")
    assert not (tmp_local / "menus" / "old.json").exists()
    assert (tmp_local / "menus" / "deleted" / "old.json").exists()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_menu.py -v
```

Expected: `test_normalize_item_basic` and `test_load_menu` FAIL (`AssertionError: assert 'price' not in {'price': 9.5, ...}`).

- [ ] **Step 3: Remove price from normalize_item in menu.py**

Replace the `normalize_item` function:

```python
def normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    name = raw.get("name") or raw.get("name_de") or raw.get("name_en") or ""
    return {
        "name": str(name).strip(),
        "extras": [str(e) for e in (raw.get("extras") or []) if e],
        "printer": str(raw.get("printer", "")).strip(),
        "bg_color": str(raw.get("bg_color", "")).strip(),
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_menu.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -q
```

Expected: 33 passed.

- [ ] **Step 6: Commit**

```bash
git -C .worktrees/remake add menu.py tests/test_menu.py
git -C .worktrees/remake commit -m "feat: remove price from menu item schema"
```

---

### Task 2: Rewrite menu_editor.html

**Files:**
- Modify: `templates/menu_editor.html` — full rewrite

**Layout approach (single set of fields, CSS-only switching):**

- The card always contains: a mobile-only header div (drag + name label + delete), a fields row (wide: flex row with drag/name/printer/color/delete; mobile: left column with labels + inputs), and an extras section (wide: collapsible `<details>`; mobile: right column, always visible).
- `display:none` on `.item-mobile-hdr` and `display:none` on `.wide-drag` / `.wide-del` achieve the layout switch.
- CSS `@media (max-width:639px)` converts `.item-card` to a 2-column CSS Grid.
- `details > *:not(summary) { display: block !important }` forces extras always visible on mobile.
- SortableJS `handle: '.drag-handle'` works correctly because `display:none` elements don't receive pointer events — on wide the mobile drag handle is invisible; on mobile the wide drag handle is invisible.

- [ ] **Step 1: Replace templates/menu_editor.html**

```html
{% extends "base.html" %}
{% block title %}Speisekarte bearbeiten{% endblock %}
{% block head %}
<script src="https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js"></script>
<style>
  /* ── Shared ── */
  .item-card {
    border: 1px solid #d0d8f0; border-radius: 10px;
    padding: 10px 12px; background: #fcfdff; margin-bottom: 10px;
    display: flex; flex-direction: column;
  }
  .drag-handle {
    color: #aaa; cursor: grab; font-size: 18px;
    user-select: none; flex-shrink: 0; line-height: 1;
  }
  .drag-handle:active { cursor: grabbing; }
  .extra-drag-handle {
    color: #bbb; cursor: grab; font-size: 14px;
    user-select: none; flex-shrink: 0;
  }
  .extra-drag-handle:active { cursor: grabbing; }
  .field-name {
    flex: 1; padding: 6px 8px; border: 1px solid #ccc;
    border-radius: 6px; font-size: 14px; min-width: 0;
  }
  .field-printer {
    padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px;
    font-size: 14px; min-width: 90px; flex-shrink: 0;
  }
  .field-bg {
    width: 38px; height: 32px; padding: 2px;
    border: 1px solid #ccc; border-radius: 6px; cursor: pointer; flex-shrink: 0;
  }
  .btn-danger {
    background: #fdd; color: #c00; border: 1px solid #f3bcbc;
    border-radius: 6px; padding: 5px 9px; cursor: pointer; font-size: 13px; flex-shrink: 0;
  }
  .btn-add-extra {
    background: none; border: 1px dashed #aab; border-radius: 6px;
    padding: 4px 10px; cursor: pointer; font-size: 12px; color: #556; margin-top: 4px;
  }
  .extra-row { display: flex; gap: 6px; align-items: center; }
  .extra-row input {
    flex: 1; padding: 5px 8px; border: 1px solid #ccc;
    border-radius: 6px; font-size: 14px;
  }
  .extras-list { display: flex; flex-direction: column; gap: 5px; }

  /* ── Wide (≥640px): Option C ── */
  .item-mobile-hdr { display: none; }
  .mobile-lbl { display: none; }
  .item-fields { display: flex; align-items: center; gap: 8px; }
  .item-extras { margin-top: 8px; margin-left: 26px; }
  .extras-summary {
    font-size: 12px; font-weight: 600; color: #666;
    cursor: pointer; user-select: none; list-style: none;
  }
  .extras-summary::marker { display: none; }

  /* ── Narrow (<640px): Option B ── */
  @media (max-width: 639px) {
    .item-card {
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: auto 1fr;
      gap: 8px;
    }
    .item-mobile-hdr {
      grid-column: 1 / -1; grid-row: 1;
      display: flex; align-items: center; gap: 8px;
    }
    .wide-drag { display: none; }
    .wide-del  { display: none; }
    .item-fields {
      grid-column: 1; grid-row: 2;
      flex-direction: column; align-items: flex-start; gap: 6px;
    }
    .item-fields .field-name,
    .item-fields .field-printer { width: 100%; box-sizing: border-box; min-width: 0; }
    .mobile-lbl {
      display: block; font-size: 11px; font-weight: 700;
      color: #666; text-transform: uppercase;
    }
    .item-extras { grid-column: 2; grid-row: 2; margin: 0; }
    /* Always show extras — override UA <details> hiding */
    .extras-details > summary { display: none; }
    .extras-details > *:not(summary) { display: block !important; }
    .extras-list { display: flex !important; flex-direction: column; gap: 5px; }
  }
</style>
{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar">
    <h1>Speisekarte bearbeiten</h1>
    <a href="/menus" class="btn">Zurück</a>
  </header>

  {% if error %}<div class="card" style="background:#ffefef;border-color:#f3bcbc">{{ error }}</div>{% endif %}

  <form method="post" action="/menus/save" class="stack" id="menu-form">
    <input type="hidden" name="loaded_file" value="{{ loaded_file }}">
    <section class="card stack">
      <label>Menü-Name:
        <input type="text" name="menu_name" value="{{ menu_name }}" required
          style="margin-left:8px;padding:6px;border:1px solid #ccc;border-radius:6px">
      </label>
    </section>

    <section class="card stack">
      <h2>Items</h2>
      <div id="items-container"></div>
      <button type="button" id="add-item" class="btn">+ Item hinzufügen</button>
    </section>

    <input type="hidden" name="items_json" id="items-json">
    <button type="submit" class="btn primary">Speichern</button>
  </form>
</div>

<script>
const PRINTER_NAMES = {{ printer_names|tojson }};
const EXISTING_ITEMS = {{ items|tojson }};

function printerOptions(selected) {
  const none = '<option value="">— kein Drucker —</option>';
  return none + PRINTER_NAMES.map(p =>
    `<option value="${p}"${p === selected ? ' selected' : ''}>${p}</option>`
  ).join('');
}

function updateSummary(extrasSection) {
  const summary = extrasSection.querySelector('.extras-summary');
  if (!summary) return;
  const count = extrasSection.querySelectorAll('.field-extra').length;
  summary.textContent = (count > 0 ? '▾' : '▸') + ' Extras (' + count + ')';
}

function makeExtraRow(value) {
  const div = document.createElement('div');
  div.className = 'extra-row';
  const handle = document.createElement('span');
  handle.className = 'extra-drag-handle';
  handle.textContent = '⠿';
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'field-extra';
  input.placeholder = 'z. B. ohne Zwiebeln';
  input.value = value || '';
  const rm = document.createElement('button');
  rm.type = 'button';
  rm.className = 'btn-danger';
  rm.textContent = '✕';
  rm.addEventListener('click', () => {
    const section = div.closest('.item-extras');
    div.remove();
    if (section) updateSummary(section);
  });
  div.appendChild(handle);
  div.appendChild(input);
  div.appendChild(rm);
  return div;
}

function makeItemCard(item) {
  item = item || { name: '', printer: '', bg_color: '#ffffff', extras: [] };
  const extras = item.extras || [];
  const card = document.createElement('div');
  card.className = 'item-card';

  // ── Mobile-only header (hidden on wide via CSS) ──
  const mobileHdr = document.createElement('div');
  mobileHdr.className = 'item-mobile-hdr';
  const mobileDragHandle = document.createElement('span');
  mobileDragHandle.className = 'drag-handle';
  mobileDragHandle.textContent = '⠿';
  const nameLbl = document.createElement('span');
  nameLbl.style.cssText = 'font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
  nameLbl.textContent = item.name || 'Neues Item';
  const mobileDel = document.createElement('button');
  mobileDel.type = 'button';
  mobileDel.className = 'btn-danger remove-item';
  mobileDel.textContent = '✕';
  mobileHdr.appendChild(mobileDragHandle);
  mobileHdr.appendChild(nameLbl);
  mobileHdr.appendChild(mobileDel);
  card.appendChild(mobileHdr);

  // ── Fields row (wide: flex row; mobile: left column via CSS grid) ──
  const fieldsRow = document.createElement('div');
  fieldsRow.className = 'item-fields';

  const wideDrag = document.createElement('span');
  wideDrag.className = 'drag-handle wide-drag';
  wideDrag.textContent = '⠿';

  const nameLblEl = document.createElement('label');
  nameLblEl.className = 'mobile-lbl';
  nameLblEl.textContent = 'Name';

  const nameInput = document.createElement('input');
  nameInput.className = 'field-name';
  nameInput.type = 'text';
  nameInput.placeholder = 'Name';
  nameInput.value = item.name || '';

  const printerLblEl = document.createElement('label');
  printerLblEl.className = 'mobile-lbl';
  printerLblEl.textContent = 'Drucker';

  const printerSel = document.createElement('select');
  printerSel.className = 'field-printer';
  printerSel.innerHTML = printerOptions(item.printer || '');

  const colorLblEl = document.createElement('label');
  colorLblEl.className = 'mobile-lbl';
  colorLblEl.textContent = 'Farbe';

  const colorInput = document.createElement('input');
  colorInput.className = 'field-bg';
  colorInput.type = 'color';
  colorInput.value = item.bg_color || '#ffffff';

  const wideDel = document.createElement('button');
  wideDel.type = 'button';
  wideDel.className = 'btn-danger remove-item wide-del';
  wideDel.textContent = '✕';

  fieldsRow.appendChild(wideDrag);
  fieldsRow.appendChild(nameLblEl);
  fieldsRow.appendChild(nameInput);
  fieldsRow.appendChild(printerLblEl);
  fieldsRow.appendChild(printerSel);
  fieldsRow.appendChild(colorLblEl);
  fieldsRow.appendChild(colorInput);
  fieldsRow.appendChild(wideDel);
  card.appendChild(fieldsRow);

  // Keep mobile name label in sync with name input
  nameInput.addEventListener('input', () => {
    nameLbl.textContent = nameInput.value || 'Neues Item';
  });

  // ── Extras section (wide: below fields; mobile: right column via CSS grid) ──
  const extrasSection = document.createElement('div');
  extrasSection.className = 'item-extras';

  const details = document.createElement('details');
  details.className = 'extras-details';
  details.open = true;

  const summary = document.createElement('summary');
  summary.className = 'extras-summary';

  const extrasList = document.createElement('div');
  extrasList.className = 'extras-list';
  extras.forEach(ex => extrasList.appendChild(makeExtraRow(ex)));

  const addExtraBtn = document.createElement('button');
  addExtraBtn.type = 'button';
  addExtraBtn.className = 'btn-add-extra';
  addExtraBtn.textContent = '+ Extra';
  addExtraBtn.addEventListener('click', () => {
    extrasList.appendChild(makeExtraRow(''));
    updateSummary(extrasSection);
    details.open = true;
  });

  details.appendChild(summary);
  details.appendChild(extrasList);
  details.appendChild(addExtraBtn);
  extrasSection.appendChild(details);
  updateSummary(extrasSection);
  card.appendChild(extrasSection);

  // Wire remove buttons
  card.querySelectorAll('.remove-item').forEach(btn => {
    btn.addEventListener('click', () => card.remove());
  });

  // SortableJS for extras list
  if (typeof Sortable !== 'undefined') {
    new Sortable(extrasList, { handle: '.extra-drag-handle', animation: 150 });
  }

  return card;
}

const container = document.getElementById('items-container');
(EXISTING_ITEMS.length ? EXISTING_ITEMS : [null]).forEach(item => {
  container.appendChild(makeItemCard(item));
});

if (typeof Sortable !== 'undefined') {
  new Sortable(container, { handle: '.drag-handle', animation: 150 });
}

document.getElementById('add-item').addEventListener('click', () => {
  container.appendChild(makeItemCard(null));
});

document.getElementById('menu-form').addEventListener('submit', () => {
  const items = Array.from(document.querySelectorAll('.item-card')).map(card => ({
    name: (card.querySelector('.field-name').value || '').trim(),
    printer: card.querySelector('.field-printer').value || '',
    bg_color: card.querySelector('.field-bg').value || '#ffffff',
    extras: Array.from(card.querySelectorAll('.field-extra'))
      .map(i => i.value.trim()).filter(Boolean),
  })).filter(it => it.name);
  document.getElementById('items-json').value = JSON.stringify(items);
});
</script>
{% endblock %}
```

- [ ] **Step 2: Run smoke tests**

```bash
uv run pytest tests/test_smoke.py -v
```

Expected: all smoke tests PASS.

- [ ] **Step 3: Manual verification**

Start the server:
```bash
uv run uvicorn app:app --port 5099 --reload
```

Open `http://localhost:5099/menus/editor` and verify:
- No price field visible
- Each extra has its own text input with drag handle and remove button
- Items can be reordered by dragging the `⠿` handle
- Extras within an item can be reordered by dragging the `⠿` handle
- Extras section collapses/expands on wide screen
- Resizing the browser window below 640px: card switches to two-column layout, extras always visible (no collapse toggle)
- Saving a menu round-trips correctly (no price in saved JSON)

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/ -q
```

Expected: 33 passed.

- [ ] **Step 5: Commit**

```bash
git -C .worktrees/remake add templates/menu_editor.html
git -C .worktrees/remake commit -m "feat: rework menu editor — no price, per-extra fields, sortable drag-and-drop, responsive layout"
```
