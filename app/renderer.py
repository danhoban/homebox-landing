import codecs
import html
import os
import string
import urllib.parse
from typing import Any

import markdown as _md

_md_renderer = _md.Markdown(extensions=["tables", "fenced_code", "nl2br"])

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_template_cache: dict[str, string.Template] = {}


def _load_template(name: str) -> string.Template:
    if name not in _template_cache:
        path = os.path.join(_TEMPLATE_DIR, name)
        with open(path, encoding="utf-8") as f:
            _template_cache[name] = string.Template(f.read())
    return _template_cache[name]


def _rot13(text: str) -> str:
    return codecs.encode(text, "rot_13")


def _css_obfuscate(display_text: str) -> str:
    mid = len(display_text) // 2
    part1 = display_text[:mid]
    part2 = display_text[mid:]
    return (
        f'<span>{part1}</span>'
        f'<span aria-hidden="true" style="display:none">REMOVE</span>'
        f'<span>{part2}</span>'
    )


def render_contact_link(contact: dict) -> str:
    ctype = contact["type"]
    label = contact["label"]
    value = contact["value"]

    if ctype == "email":
        href = f"mailto:{value}"
        display = value
    elif ctype == "tel":
        href = f"tel:{value}"
        display = value
    else:
        href = value
        display = label

    encoded_href = _rot13(href)
    obfuscated_display = _css_obfuscate(display)

    return (
        f'<a class="contact-link" data-contact="{encoded_href}" href="#">'
        f'<span class="contact-label">{label}</span>'
        f'<span class="contact-value">{obfuscated_display}</span>'
        f'</a>'
    )


def _render_tags_html(tags: list[dict]) -> str:
    if not tags:
        return ""
    pills = []
    for i, tag in enumerate(tags):
        cls = "tag-teal" if i % 2 else "tag-green"
        name = html.escape(tag.get("name", ""))
        pills.append(f'<span class="tag {cls}">{name}</span>')
    return '<div class="tags">' + "".join(pills) + "</div>"


def _is_safe_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _render_fields_html(fields: list[dict], exclude: list[str] | None = None) -> str:
    exclude_lower = {e.lower() for e in (exclude or [])}
    cards = []
    for field in fields:
        name = field.get("name", "")
        if name.lower() in exclude_lower:
            continue
        value = field.get("textValue") or field.get("value") or ""
        if not value:
            continue
        if _is_safe_url(value):
            safe_href = html.escape(value)
            rendered_value = f'<a class="field-link" href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_href}</a>'
        else:
            rendered_value = html.escape(value)
        cards.append(
            f'<div class="field-card">'
            f'<div class="field-label">{html.escape(name)}</div>'
            f'<div class="field-value">{rendered_value}</div>'
            f'</div>'
        )
    if not cards:
        return ""
    return '<div class="fields-grid">' + "".join(cards) + "</div>"


def _render_markdown(text: str) -> str:
    _md_renderer.reset()
    return _md_renderer.convert(text)


def _owner_notified_badge() -> str:
    return (
        '<div class="notify-badge">'
        '<span class="notify-dot"></span>'
        'Owner notified'
        '</div>'
    )


def render(template_name: str, context: dict[str, Any], contacts: list[dict]) -> str:
    contact_links_html = "\n".join(render_contact_link(c) for c in contacts)

    page_title = context.get("page_title", "")

    inner_tpl = _load_template(template_name)
    inner_ctx = {**context, "contact_links": contact_links_html}
    body_content = inner_tpl.safe_substitute(inner_ctx)

    base_tpl = _load_template("base.html")
    full_ctx = {
        "body_content": body_content,
        "page_title": page_title,
    }
    return base_tpl.safe_substitute(full_ctx)


def build_plant_context(item: dict) -> dict:
    fields = item.get("fields") or []
    latin_name = html.escape(next(
        (f.get("textValue", "") for f in fields if f.get("name", "").lower() == "latin name"),
        "",
    ))

    attachments = item.get("attachments") or []
    photo = next((a for a in attachments if a.get("type") == "photo"), None)
    if photo:
        photo_url = f"/landing/photo/{item['id']}/{photo['id']}"
        alt = html.escape(item.get("name", ""))
        hero_html = f'<img class="hero-image" src="{photo_url}" alt="{alt}">'
    else:
        hero_html = '<div class="hero-placeholder"></div>'

    fields_html = _render_fields_html(fields, exclude=["latin name"])
    fields_section_html = ""
    if fields_html:
        fields_section_html = (
            '<div class="divider"></div>'
            '<div class="section">'
            '<div class="section-label">Details</div>'
            + fields_html +
            '</div>'
        )

    care_notes = item.get("notes") or ""
    care_section_html = ""
    if care_notes:
        care_section_html = (
            '<div class="divider"></div>'
            '<div class="section">'
            '<div class="section-label">Care notes</div>'
            f'<div class="care-notes md-content">{_render_markdown(care_notes)}</div>'
            '</div>'
        )

    return {
        "page_title": html.escape(item.get("name", "Plant")),
        "item_name": html.escape(item.get("name", "")),
        "latin_name": latin_name,
        "description": html.escape(item.get("description") or ""),
        "tags_html": _render_tags_html(item.get("tags") or []),
        "hero_html": hero_html,
        "fields_section_html": fields_section_html,
        "care_section_html": care_section_html,
        "owner_notified_badge": "",
    }


def build_item_context(item: dict, asset_id: str = "") -> dict:
    return {
        "page_title": html.escape(item.get("name", "Lost item")),
        "item_name": html.escape(item.get("name", "")),
        "description": html.escape(item.get("description") or ""),
        "asset_id": html.escape(asset_id),
        "owner_notified_badge": _owner_notified_badge(),
    }


def build_fallback_context() -> dict:
    return {
        "page_title": "Get in touch",
        "owner_notified_badge": "",
    }


def build_not_found_context() -> dict:
    return {
        "page_title": "Not found",
        "owner_notified_badge": "",
    }
