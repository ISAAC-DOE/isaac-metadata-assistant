"""Turn an exported question site (``isaac bundle site export``) into the documents the artifact page reads, and
turn the artifact's saved answers back into the site's ``answers.json``.

    python seed.py cards <export>/data/site-data.json <out_dir> [--image-urls urls.json]
        writes <out_dir>/meta/site.json and <out_dir>/cards/<card_id>.json, one file per document, for
        ArtifactData writes (collection = the folder, doc_id = the file name). Lists the images to upload.
        `covers` (how an answer becomes decisions) stays local: it is not written.
    python seed.py answers <site-data.json> <read_dir> <answers.json>
        <read_dir> is an ArtifactData read with out_dir (``<read_dir>/answers/*.json``, ``<read_dir>/log/*.json``).
        Writes the contract's answers.json, ready for ``isaac bundle site import``.

The output holds whatever the export holds (real beamtime details): write it outside any git working tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ANSWER_KEYS = ("card_id", "action", "value", "typed", "note", "by", "at")


def _public(card: dict, order: int, urls: dict) -> dict:
    out = {k: v for k, v in card.items() if k != "covers"}
    out["order"] = order
    ctx = []
    for item in out.get("context") or ():
        if item.get("kind") == "image":
            url = urls.get(item.get("image"))
            if not url:
                continue  # an image that was not uploaded is left out, never shown broken
            item = {**item, "image_url": url}
        ctx.append(item)
    out["context"] = ctx
    return out


def cards(site_data: Path, out_dir: Path, image_urls: Path | None) -> None:
    site = json.loads(site_data.read_text(encoding="utf-8"))
    urls = json.loads(image_urls.read_text(encoding="utf-8")) if image_urls else {}
    (out_dir / "meta").mkdir(parents=True, exist_ok=True)
    (out_dir / "cards").mkdir(parents=True, exist_ok=True)
    meta = {k: site.get(k) for k in ("bundle_id", "bundle_version", "title", "generated_at", "totals", "sections")}
    (out_dir / "meta" / "site.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    images = set()
    for n, card in enumerate(site.get("cards") or ()):
        for item in card.get("context") or ():
            if item.get("kind") == "image" and item.get("image"):
                images.add(item["image"])
        doc = _public(card, n, urls)
        body = json.dumps(doc, ensure_ascii=False)
        if len(body.encode()) > 250_000:
            raise SystemExit(f"card {card['card_id']} is {len(body.encode())} bytes, over the store's 256 KiB document limit")
        (out_dir / "cards" / f"{card['card_id']}.json").write_text(body)
    ordered = sorted(images)
    print(f"{len(site.get('cards') or ())} cards, 1 meta document -> {out_dir}")
    if ordered:
        print(f"{len(ordered)} image file(s) to upload as artifact assets:")
        for i in ordered:
            print(f"  {site_data.parent / i}" + ("" if i in urls else "   (no URL yet: left out of the cards)"))
        left = [i for i in ordered if i not in urls]
        if left:
            print(f"Upload them, put each URL in a json map {{\"img/<sha>.png\": \"<url>\"}}, and rerun with --image-urls.")


def _docs(folder: Path) -> list[dict]:
    out = []
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        raw = json.loads(p.read_text(encoding="utf-8"))
        doc = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        out.append(doc)
    return out


def answers(site_data: Path, read_dir: Path, out: Path) -> None:
    site = json.loads(site_data.read_text(encoding="utf-8"))
    current = [{k: d.get(k) for k in ANSWER_KEYS} for d in _docs(read_dir / "answers") if d.get("card_id")]
    log = [{k: d.get(k) for k in ANSWER_KEYS} for d in _docs(read_dir / "log") if d.get("card_id")]
    current.sort(key=lambda a: str(a.get("at") or ""))
    log.sort(key=lambda a: str(a.get("at") or ""))
    doc = {"format": "isaac.question_site_answers", "format_version": "1.0.0", "bundle_id": site["bundle_id"],
           "bundle_version": site.get("bundle_version"), "exported_at": max([a["at"] for a in log if a.get("at")] or [None]),
           "answers": current, "log": log}
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"{len(current)} current answer(s), {len(log)} log entr(ies) -> {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["cards"] and len(a) in (3, 5):
        cards(Path(a[1]), Path(a[2]), Path(a[4]) if len(a) == 5 and a[3] == "--image-urls" else None)
    elif a[:1] == ["answers"] and len(a) == 4:
        answers(Path(a[1]), Path(a[2]), Path(a[3]))
    else:
        raise SystemExit(__doc__)
