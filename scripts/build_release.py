#!/usr/bin/env python3
"""Validate Talkami public learning content and build deterministic GitHub Release assets.

The Android app treats these files as untrusted remote content. This builder therefore mirrors
its important limits and rejects malformed, ambiguous, or executable package contents before a
Release can be published.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CONTENT = ROOT / "content"

MAX_BOOK_BYTES = 512 * 1024 * 1024
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_LESSON_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_BYTES = 200 * 1024 * 1024
MAX_UNPACKED_BYTES = 500 * 1024 * 1024
MAX_PACKAGE_ENTRY_BYTES = 80 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 5000
MAX_EXERCISES = 120
MAX_OPTIONS = 12
MAX_WORDS = 40
MAX_PAIRS = 16
MAX_ACCEPTED_ANSWERS = 16
MAX_COURSES = 48
MAX_UNITS_PER_COURSE = 120
MAX_LESSONS_PER_COURSE = 240
MAX_REQUIREMENTS = 16

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
UPDATED_AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_EXERCISES = {
    "single_choice", "listen_choice", "true_false", "word_order",
    "fill_blank", "matching", "dictation", "image_choice",
}
ALLOWED_LESSON_TYPES = {
    "normal", "review", "practice", "test", "speaking", "listening",
    "story", "chest", "checkpoint", "trophy",
}
ALLOWED_POSITIONS = {"left", "center", "right"}
IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".wav", ".webm"}
EXECUTABLE_EXTENSIONS = {".apk", ".aab", ".dex", ".so", ".jar", ".class", ".sh"}

CLAIMED_ASSETS = {
    "words-catalog.json",
    "speaking-catalog.json",
    "patterns-catalog.json",
    "books-catalog.json",
    "learning-path-catalog.json",
    "learning-home.json",
    "content-metadata.json",
    "ai-course-catalog.json",
}
BUILD_STATS: dict[str, int] = {
    "word_packs": 0,
    "words": 0,
    "speaking_packs": 0,
    "phrases": 0,
    "pattern_categories": 0,
    "patterns": 0,
    "books": 0,
    "home_slides": 0,
    "learning_packages": 0,
    "courses": 0,
    "units": 0,
    "lessons": 0,
    "exercises": 0,
    "ai_course_categories": 0,
    "ai_course_scenes": 0,
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def load_json(path: Path) -> Any:
    if not path.is_file():
        fail(f"Missing JSON file: {path}")
    if path.stat().st_size <= 0:
        fail(f"Empty JSON file: {path}")
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except UnicodeDecodeError as exc:
        fail(f"JSON must be UTF-8: {path}: {exc}")
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path}: {exc}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def compact_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_list(value: Any, label: str, minimum: int = 0, maximum: int | None = None) -> list[Any]:
    if not isinstance(value, list):
        fail(f"{label} must be an array")
    if len(value) < minimum:
        fail(f"{label} must contain at least {minimum} item(s)")
    if maximum is not None and len(value) > maximum:
        fail(f"{label} contains too many items: {len(value)} > {maximum}")
    return value


def require_text(value: Any, label: str, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"Missing or empty {label}")
    text = value.strip()
    if maximum is not None and len(text) > maximum:
        fail(f"{label} is too long: {len(text)} > {maximum}")
    return text


def optional_text(value: Any, label: str, maximum: int | None = None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        fail(f"{label} must be text")
    text = value.strip()
    if maximum is not None and len(text) > maximum:
        fail(f"{label} is too long: {len(text)} > {maximum}")
    return text


def require_version(value: Any, label: str) -> int:
    if isinstance(value, bool):
        fail(f"{label} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError):
        fail(f"{label} must be an integer")
    if number <= 0:
        fail(f"{label} must be greater than zero")
    return number


def require_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        fail(f"{label} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError):
        fail(f"{label} must be an integer")
    if number < minimum or number > maximum:
        fail(f"{label} must be between {minimum} and {maximum}: {number}")
    return number


def require_safe_id(value: Any, label: str) -> str:
    text = require_text(value, label, 80)
    if not SAFE_ID.fullmatch(text) or text.endswith(".") or text in {".", ".."}:
        fail(f"{label} must use only letters, numbers, dot, underscore, or hyphen: {text}")
    return text


def safe_asset_name(value: Any, label: str) -> str:
    text = require_text(value, label, 255)
    if "\\" in text or any(ord(ch) < 32 for ch in text):
        fail(f"{label} contains unsupported characters: {text}")
    path = PurePosixPath(text)
    if path.is_absolute() or len(path.parts) != 1 or path.name in {".", ".."}:
        fail(f"{label} must be a plain file name: {text}")
    return text


def safe_relative_path(value: Any, label: str, require_file: bool = True) -> str:
    text = require_text(value, label, 512).replace("\\", "/")
    if text.startswith("/") or ":" in text or "\x00" in text:
        fail(f"{label} must be a safe relative path: {text}")
    path = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in path.parts):
        fail(f"{label} contains an unsafe path component: {text}")
    if require_file and text.endswith("/"):
        fail(f"{label} must point to a file: {text}")
    return path.as_posix()


def claim_asset(value: Any, label: str) -> str:
    name = safe_asset_name(value, label)
    key = name.lower()
    if key in CLAIMED_ASSETS:
        fail(f"Duplicate or reserved release asset name: {name}")
    CLAIMED_ASSETS.add(key)
    return name


def source_file(value: Any, label: str) -> Path:
    text = require_text(value, label, 512)
    candidate = (ROOT / text).resolve()
    content_root = CONTENT.resolve()
    try:
        candidate.relative_to(content_root)
    except ValueError:
        fail(f"{label} must stay inside the content directory: {text}")
    if not candidate.is_file():
        fail(f"Missing {label}: {candidate}")
    if candidate.is_symlink():
        fail(f"Symlinks are not allowed for {label}: {candidate}")
    return candidate


def ensure_normal_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        fail(f"{label} must be a regular file: {path}")
    # Source file modes vary between Windows ZIP uploads and Git checkouts. The release ZIP
    # always normalizes entries to 0644, so reject executable *types* rather than an inherited bit.
    if path.suffix.lower() in EXECUTABLE_EXTENSIONS:
        fail(f"Executable file type is not allowed in remote content: {path}")


def walk_catalog_items(items: Iterable[dict[str, Any]] | None):
    for item in items or []:
        require_dict(item, "catalog item")
        yield item
        children = item.get("children", [])
        if children is not None:
            yield from walk_catalog_items(require_list(children, "catalog children"))


def validate_catalog_ids(items: list[dict[str, Any]], catalog_name: str) -> None:
    seen: set[str] = set()
    for item in walk_catalog_items(items):
        item_id = require_safe_id(item.get("id"), f"{catalog_name} item id")
        if item_id in seen:
            fail(f"Duplicate {catalog_name} catalog id: {item_id}")
        seen.add(item_id)


def validate_unique_records(records: list[dict[str, Any]], id_key: str, order_key: str | None,
                            label: str) -> None:
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for index, record in enumerate(records, start=1):
        require_dict(record, f"{label} #{index}")
        record_id = require_safe_id(record.get(id_key), f"{label} #{index} {id_key}")
        if record_id in seen_ids:
            fail(f"Duplicate {label} id: {record_id}")
        seen_ids.add(record_id)
        if order_key:
            order = require_int(record.get(order_key), f"{label} {record_id} order", 1, 1_000_000)
            if order in seen_orders:
                fail(f"Duplicate {label} order: {order}")
            seen_orders.add(order)


def _load_loose_word_json(path: Path) -> Any:
    """Load normal JSON or the legacy HSK object-stream format.

    Older HSK source files were maintained as:
      { ... },
      { ... },
      { ... }
    without a surrounding array.  Keep accepting that maintainer-friendly
    source format, but always emit valid JSON release assets.
    """
    if not path.is_file():
        fail(f"Missing JSON file: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        fail(f"Empty JSON file: {path}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    values: list[Any] = []
    cursor = 0
    length = len(raw)
    while cursor < length:
        while cursor < length and (raw[cursor].isspace() or raw[cursor] == ","):
            cursor += 1
        if cursor >= length:
            break
        # Some legacy exports kept a dangling closing array/object suffix even
        # though the opening wrapper was removed. Accept only pure trailing
        # closers here; any other malformed content still fails below.
        if raw[cursor] in "]}":
            trailing = raw[cursor:]
            if all(ch.isspace() or ch in ",]}" for ch in trailing):
                break
        try:
            value, cursor = decoder.raw_decode(raw, cursor)
        except json.JSONDecodeError as exc:
            fail(f"Invalid JSON in {path}: {exc}")
        values.append(value)
    if not values:
        fail(f"No word records found in {path}")
    return values


def _word_record_id(value: Any, label: str) -> str:
    if isinstance(value, bool):
        fail(f"{label} must be a positive integer or safe text id")
    if isinstance(value, int):
        if value <= 0:
            fail(f"{label} must be greater than zero")
        return str(value)
    return require_safe_id(value, label)


def _validate_word_records(words: list[Any], source_data: Path, level: str) -> None:
    seen_ids: set[str] = set()
    expected_numeric_level = level[3:] if re.fullmatch(r"hsk[1-9]", level, re.IGNORECASE) else ""

    for index, raw_word in enumerate(words, start=1):
        word = require_dict(raw_word, f"word #{index} in {source_data.name}")
        word_id = _word_record_id(word.get("id", index), f"word id in {source_data.name}")
        if word_id in seen_ids:
            fail(f"Duplicate word id in {source_data.name}: {word_id}")
        seen_ids.add(word_id)

        # Lightweight HSK source: id / hanzi / burmese / examples / level.
        if word.get("hanzi") is not None or word.get("burmese") is not None:
            require_text(word.get("hanzi"), f"hanzi for {word_id}", 260)
            require_text(word.get("burmese"), f"Myanmar meaning for {word_id}", 1200)
            optional_text(word.get("pinyin"), f"legacy pinyin for {word_id}", 260)
            optional_text(word.get("pinyin_override"), f"pinyin override for {word_id}", 260)
            source_level = optional_text(word.get("level"), f"level for {word_id}", 32)
            if expected_numeric_level and source_level and source_level != expected_numeric_level:
                fail(
                    f"Word level mismatch for {word_id}: expected {expected_numeric_level}, got {source_level}"
                )
            examples = require_list(word.get("examples", []), f"examples for {word_id}", 0, 12)
            for example_index, raw_example in enumerate(examples, start=1):
                example = require_dict(raw_example, f"example #{example_index} for {word_id}")
                require_text(example.get("hanzi"), f"example hanzi for {word_id}", 1200)
                require_text(example.get("burmese"), f"example Myanmar for {word_id}", 2400)
                optional_text(example.get("pinyin"), f"example pinyin for {word_id}", 1200)
                optional_text(example.get("pinyin_override"), f"example pinyin override for {word_id}", 1200)
            continue

        # Existing rich format remains supported. Pinyin is optional because the
        # web client now generates it from Chinese text.
        require_text(word.get("word"), f"word text for {word_id}", 260)
        optional_text(word.get("pinyin_override"), f"pinyin override for {word_id}", 260)
        optional_text(word.get("pinyin"), f"pinyin for {word_id}", 260)
        require_text(word.get("meaning_my"), f"Myanmar meaning for {word_id}", 1200)
        example = optional_text(word.get("example"), f"example for {word_id}", 1200)
        optional_text(word.get("example_pinyin_override"), f"example pinyin override for {word_id}", 1200)
        optional_text(word.get("example_pinyin"), f"example pinyin for {word_id}", 1200)
        if example:
            optional_text(word.get("example_my"), f"example Myanmar for {word_id}", 2400)


def build_words() -> None:
    source_path = CONTENT / "words" / "catalog.json"
    source = require_dict(load_json(source_path), "word catalog")
    require_version(source.get("version"), "word catalog version")
    items = require_list(source.get("items"), "word catalog items")
    validate_catalog_ids(items, "word")
    result = copy.deepcopy(source)
    used_output_names: set[str] = set()

    for item in walk_catalog_items(result.get("items", [])):
        source_data_value = item.pop("source_data", "")
        source_cover_value = item.pop("source_cover", "")
        if not source_data_value:
            continue
        item_id = require_safe_id(item.get("id"), "word item id")
        if item.get("target") != "word":
            fail(f"Word leaf {item_id} must use target=word")
        level = require_safe_id(item.get("level"), f"word catalog level for {item_id}")
        data_url = safe_asset_name(item.get("data_url"), f"data_url for {item_id}")
        cover_url = safe_asset_name(item.get("cover_url"), f"cover_url for {item_id}")
        require_version(item.get("cover_version"), f"cover_version for {item_id}")
        catalog_data_version = require_version(item.get("data_version"), f"data_version for {item_id}")
        if Path(cover_url).suffix.lower() not in IMAGE_EXTENSIONS:
            fail(f"Unsupported word cover format: {cover_url}")

        for output_name in (data_url, cover_url):
            if output_name.lower() in used_output_names:
                fail(f"Duplicate release asset name: {output_name}")
            used_output_names.add(output_name.lower())
            claim_asset(output_name, f"release asset for {item_id}")

        source_data = source_file(source_data_value, "word pack")
        source_cover = source_file(source_cover_value, "word cover")
        ensure_normal_file(source_data, "word pack")
        ensure_normal_file(source_cover, "word cover")

        raw_pack = _load_loose_word_json(source_data)
        if isinstance(raw_pack, dict):
            words = require_list(raw_pack.get("items"), f"words in {source_data}", 1)
            declared_level = optional_text(
                raw_pack.get("categoryId", raw_pack.get("pack_id")),
                f"word pack category in {source_data}",
                80,
            )
            if declared_level and declared_level != level:
                fail(f"Word pack categoryId must equal catalog level for {item_id}")
            version = require_version(raw_pack.get("version", catalog_data_version), f"word pack version in {source_data}")
            release_pack = copy.deepcopy(raw_pack)
            release_pack["categoryId"] = level
            release_pack["version"] = version
            release_pack["items"] = words
        elif isinstance(raw_pack, list):
            words = require_list(raw_pack, f"words in {source_data}", 1)
            version = catalog_data_version
            # Keep lightweight HSK release files lightweight too. The catalog
            # already carries level/version metadata, and the web parser accepts
            # a top-level array directly.
            release_pack = words
        else:
            fail(f"word pack {source_data} must be an object, array, or legacy object stream")

        _validate_word_records(words, source_data, level)

        output_data = DIST / data_url
        output_cover = DIST / cover_url
        write_json(output_data, release_pack)
        shutil.copy2(source_cover, output_cover)
        item["data_sha256"] = sha256(output_data)
        item["item_count"] = len(words)
        item["data_version"] = version
        BUILD_STATS["word_packs"] += 1
        BUILD_STATS["words"] += len(words)

    write_json(DIST / "words-catalog.json", result)


def build_speaking() -> None:
    source_path = CONTENT / "speaking" / "catalog.json"
    source = require_dict(load_json(source_path), "speaking catalog")
    require_version(source.get("version"), "speaking catalog version")
    items = require_list(source.get("items"), "speaking catalog items")
    validate_catalog_ids(items, "speaking")
    result = copy.deepcopy(source)
    used_output_names: set[str] = set()

    for item in walk_catalog_items(result.get("items", [])):
        source_value = item.pop("source_data", "")
        if not source_value:
            continue
        item_id = require_safe_id(item.get("id"), "speaking item id")
        if item.get("target") != "study":
            fail(f"Speaking leaf {item_id} must use target=study")
        data_url = safe_asset_name(item.get("data_url"), f"data_url for {item_id}")
        if data_url.lower() in used_output_names:
            fail(f"Duplicate release asset name: {data_url}")
        used_output_names.add(data_url.lower())
        claim_asset(data_url, f"release asset for {item_id}")

        source_data = source_file(source_value, "speaking pack")
        ensure_normal_file(source_data, "speaking pack")
        pack = require_dict(load_json(source_data), f"speaking pack {source_data}")
        phrases = require_list(pack.get("phrases", pack.get("items")),
                               f"phrases in {source_data}", 1)
        if pack.get("pack_id") != item_id:
            fail(f"Speaking pack_id must equal catalog id for {item_id}")
        version = require_version(pack.get("version"), f"speaking pack version in {source_data}")
        validate_unique_records(phrases, "id", None, f"phrase in {source_data.name}")
        for entry in phrases:
            phrase_id = entry.get("id")
            require_text(entry.get("text"), f"phrase text for {phrase_id}", 1200)
            require_text(entry.get("pinyin"), f"phrase pinyin for {phrase_id}", 1200)
            require_text(entry.get("meaning_my"), f"Myanmar meaning for {phrase_id}", 1200)
            if "meaning_ny" in entry:
                fail(f"Typo meaning_ny found in phrase {phrase_id}; use meaning_my")

        output_data = DIST / data_url
        shutil.copy2(source_data, output_data)
        item["data_sha256"] = sha256(output_data)
        item["item_count"] = len(phrases)
        item["data_version"] = version
        BUILD_STATS["speaking_packs"] += 1
        BUILD_STATS["phrases"] += len(phrases)

    write_json(DIST / "speaking-catalog.json", result)


PATTERN_TYPES = {
    "word_order", "function_word", "complement", "comparison", "compound",
    "question", "discourse", "tone", "quantity",
}
PATTERN_DIFFICULTIES = {"easy", "medium", "hard"}
PATTERN_PROMPT_PLACEHOLDERS = {
    "{{number}}", "{{title}}", "{{formula}}", "{{introduction}}", "{{example}}",
    "{{teaching_type}}", "{{difficulty}}", "{{focus_tags}}",
}


def _validate_pattern_leaf(item: dict[str, Any], category_id: str,
                           seen_numbers: set[int]) -> None:
    item_id = require_safe_id(item.get("id"), f"pattern id in {category_id}")
    number = require_text(item.get("number"), f"pattern number for {item_id}", 6)
    if not re.fullmatch(r"[0-9]{3,4}", number):
        fail(f"Pattern number must use zero-padded digits: {item_id} -> {number}")
    if item_id != f"pattern_{number}":
        fail(f"Pattern id must match number: expected pattern_{number}, got {item_id}")
    number_value = int(number)
    if number_value in seen_numbers:
        fail(f"Duplicate pattern number: {number}")
    seen_numbers.add(number_value)
    if item.get("target") != "ai_pattern":
        fail(f"Pattern {item_id} must use target=ai_pattern")
    require_text(item.get("title"), f"pattern title for {item_id}", 160)
    require_text(item.get("formula"), f"pattern formula for {item_id}", 500)
    require_text(item.get("introduction"), f"pattern introduction for {item_id}", 1200)
    require_text(item.get("example"), f"pattern example for {item_id}", 800)
    teaching_type = require_text(item.get("teaching_type"), f"teaching_type for {item_id}", 40)
    if teaching_type not in PATTERN_TYPES:
        fail(f"Unsupported teaching_type for {item_id}: {teaching_type}")
    difficulty = require_text(item.get("difficulty"), f"difficulty for {item_id}", 20)
    if difficulty not in PATTERN_DIFFICULTIES:
        fail(f"Unsupported difficulty for {item_id}: {difficulty}")
    tags = require_list(item.get("focus_tags", []), f"focus_tags for {item_id}", 0, 8)
    normalized_tags: set[str] = set()
    for tag_index, tag in enumerate(tags, start=1):
        value = require_text(tag, f"focus tag #{tag_index} for {item_id}", 60)
        if value in normalized_tags:
            fail(f"Duplicate focus tag for {item_id}: {value}")
        normalized_tags.add(value)
    if item.get("children"):
        fail(f"Pattern leaf must not contain children: {item_id}")


def build_patterns() -> None:
    source_path = CONTENT / "patterns" / "catalog.json"
    if not source_path.is_file():
        return
    source = require_dict(load_json(source_path), "pattern catalog")
    require_version(source.get("version"), "pattern catalog version")
    updated_at = require_text(source.get("updated_at"), "pattern catalog updated_at", 40)
    if not UPDATED_AT.fullmatch(updated_at):
        fail("pattern catalog updated_at must use UTC ISO format, for example 2026-08-11T06:20:00Z")
    if source.get("type") != "patterns":
        fail("pattern catalog type must be patterns")
    expected_count = require_int(source.get("item_count"), "pattern item_count", 1, 5000)
    items = require_list(source.get("items"), "pattern catalog items", 1, 100)
    validate_catalog_ids(items, "pattern")
    declared_pack_count = require_int(source.get("pack_count", len(items)),
                                      "pattern pack_count", 1, 100)
    if declared_pack_count != len(items):
        fail(f"Pattern pack_count mismatch: catalog={declared_pack_count}, actual={len(items)}")

    result = copy.deepcopy(source)
    prompt = require_dict(result.get("prompt_template"), "pattern prompt_template")
    require_version(prompt.get("version"), "pattern prompt version")
    prompt_url = safe_asset_name(prompt.get("url"), "pattern prompt url")
    if not prompt_url.lower().endswith(".txt"):
        fail("pattern prompt url must end with .txt")
    claim_asset(prompt_url, "pattern prompt release asset")
    source_prompt_value = prompt.pop("source_prompt", "")
    source_prompt = source_file(source_prompt_value, "pattern prompt")
    ensure_normal_file(source_prompt, "pattern prompt")
    if source_prompt.stat().st_size <= 0 or source_prompt.stat().st_size > 128 * 1024:
        fail("pattern prompt must be between 1 byte and 128 KiB")
    try:
        prompt_text = source_prompt.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        fail(f"pattern prompt must be UTF-8: {exc}")
    missing = sorted(token for token in PATTERN_PROMPT_PLACEHOLDERS if token not in prompt_text)
    if missing:
        fail("pattern prompt is missing placeholders: " + ", ".join(missing))
    output_prompt = DIST / prompt_url
    shutil.copy2(source_prompt, output_prompt)
    prompt["sha256"] = sha256(output_prompt)
    prompt["size"] = output_prompt.stat().st_size

    seen_numbers: set[int] = set()
    leaf_count = 0
    used_output_names: set[str] = set()
    result_categories = result.get("items", [])

    for category_index, category in enumerate(result_categories, start=1):
        require_dict(category, f"pattern category #{category_index}")
        category_id = require_safe_id(category.get("id"), f"pattern category #{category_index} id")
        require_text(category.get("title"), f"pattern category title for {category_id}", 120)
        if category.get("target") != "pattern_pack":
            fail(f"Pattern category {category_id} must use target=pattern_pack")
        if category.get("children"):
            fail(f"Pattern catalog must contain pack descriptors only; remove children from {category_id}")

        source_data_value = category.pop("source_data", "")
        data_url = safe_asset_name(category.get("data_url"), f"data_url for {category_id}")
        if not data_url.lower().endswith(".json"):
            fail(f"Pattern pack data_url must end with .json: {data_url}")
        if data_url.lower() in used_output_names:
            fail(f"Duplicate pattern release asset name: {data_url}")
        used_output_names.add(data_url.lower())
        claim_asset(data_url, f"pattern release asset for {category_id}")

        source_data = source_file(source_data_value, f"pattern pack for {category_id}")
        ensure_normal_file(source_data, f"pattern pack for {category_id}")
        if source_data.stat().st_size <= 0 or source_data.stat().st_size > MAX_CATALOG_BYTES:
            fail(f"Pattern pack must be between 1 byte and 2 MiB: {source_data}")
        pack = require_dict(load_json(source_data), f"pattern pack {source_data}")
        if pack.get("type") != "pattern_pack":
            fail(f"Pattern pack type must be pattern_pack: {source_data}")
        if pack.get("category_id") != category_id:
            fail(f"Pattern pack category_id must equal catalog id for {category_id}")
        pack_version = require_version(pack.get("version"), f"pattern pack version for {category_id}")
        pack_updated_at = require_text(pack.get("updated_at"), f"pattern pack updated_at for {category_id}", 40)
        if not UPDATED_AT.fullmatch(pack_updated_at):
            fail(f"Pattern pack updated_at must use UTC ISO format: {source_data}")
        patterns = require_list(pack.get("items"), f"patterns in {source_data}", 1, 500)
        declared_count = require_int(pack.get("item_count", len(patterns)),
                                     f"pattern pack item_count for {category_id}", 1, 500)
        if declared_count != len(patterns):
            fail(f"Pattern pack item_count mismatch for {category_id}: {declared_count} vs {len(patterns)}")

        local_ids: set[str] = set()
        for item in patterns:
            item = require_dict(item, f"pattern in {category_id}")
            item_id = require_safe_id(item.get("id"), f"pattern id in {category_id}")
            if item_id in local_ids:
                fail(f"Duplicate pattern id inside {category_id}: {item_id}")
            local_ids.add(item_id)
            _validate_pattern_leaf(item, category_id, seen_numbers)

        output_data = DIST / data_url
        shutil.copy2(source_data, output_data)
        category["data_sha256"] = sha256(output_data)
        category["item_count"] = len(patterns)
        category["data_version"] = pack_version
        badge = optional_text(category.get("badge", ""), f"pattern category badge for {category_id}", 40)
        if badge:
            digits = "".join(ch for ch in badge if ch.isdigit())
            if digits and int(digits) != len(patterns):
                fail(f"Pattern category badge count mismatch for {category_id}: {badge} vs {len(patterns)}")
        leaf_count += len(patterns)

    if leaf_count != expected_count:
        fail(f"Pattern item_count mismatch: catalog={expected_count}, actual={leaf_count}")
    expected_numbers = set(range(1, expected_count + 1))
    if seen_numbers != expected_numbers:
        missing_numbers = sorted(expected_numbers - seen_numbers)[:20]
        extra_numbers = sorted(seen_numbers - expected_numbers)[:20]
        fail(f"Pattern numbers must be continuous from 001 to {expected_count:03d}; "
             f"missing={missing_numbers}, extra={extra_numbers}")

    output = DIST / "patterns-catalog.json"
    write_json(output, result)
    if output.stat().st_size > MAX_CATALOG_BYTES:
        fail("Generated patterns-catalog.json exceeds 2 MiB")
    BUILD_STATS["pattern_categories"] += len(result_categories)
    BUILD_STATS["patterns"] += leaf_count


def build_home() -> None:
    source_path = CONTENT / "home" / "catalog.json"
    if not source_path.is_file():
        return
    source = require_dict(load_json(source_path), "learning home catalog")
    if source.get("type") != "learning_home":
        fail("learning home catalog type must be learning_home")
    require_version(source.get("version"), "learning home version")
    updated_at = require_text(source.get("updated_at"), "learning home updated_at", 40)
    if not UPDATED_AT.fullmatch(updated_at):
        fail("learning home updated_at must use UTC ISO format, e.g. 2026-08-11T09:00:00Z")

    hero = require_dict(source.get("hero"), "learning home hero")
    source_image = source_file(hero.get("source_image"), "learning home hero source_image")
    ensure_normal_file(source_image, "learning home hero image")
    if source_image.suffix.lower() not in IMAGE_EXTENSIONS:
        fail(f"learning home hero must be an image: {source_image}")
    if source_image.stat().st_size <= 0 or source_image.stat().st_size > 5 * 1024 * 1024:
        fail("learning home hero image must be between 1 byte and 5 MiB")
    image_name = claim_asset(hero.get("image_url"), "learning home image_url")
    image_version = require_version(hero.get("image_version"), "learning home image_version")

    slides = require_list(hero.get("slides"), "learning home slides", 1, 8)
    seen_ids: set[str] = set()
    for index, raw in enumerate(slides, start=1):
        slide = require_dict(raw, f"learning home slide #{index}")
        slide_id = require_safe_id(slide.get("id"), f"learning home slide #{index} id")
        if slide_id in seen_ids:
            fail(f"Duplicate learning home slide id: {slide_id}")
        seen_ids.add(slide_id)
        require_text(slide.get("title"), f"learning home slide {slide_id} title", 80)
        optional_text(slide.get("subtitle"), f"learning home slide {slide_id} subtitle", 160)
        optional_text(slide.get("price"), f"learning home slide {slide_id} price", 60)
        optional_text(slide.get("note"), f"learning home slide {slide_id} note", 160)
        for suffix in ("en", "my"):
            optional_text(slide.get(f"title_{suffix}"), f"learning home slide {slide_id} title_{suffix}", 100)
            optional_text(slide.get(f"subtitle_{suffix}"), f"learning home slide {slide_id} subtitle_{suffix}", 180)
            optional_text(slide.get(f"price_{suffix}"), f"learning home slide {slide_id} price_{suffix}", 80)
            optional_text(slide.get(f"note_{suffix}"), f"learning home slide {slide_id} note_{suffix}", 180)

    output_image = DIST / image_name
    shutil.copy2(source_image, output_image)
    result = copy.deepcopy(source)
    result_hero = require_dict(result.get("hero"), "generated learning home hero")
    result_hero.pop("source_image", None)
    result_hero["image_url"] = image_name
    result_hero["image_version"] = image_version
    result_hero["image_size"] = output_image.stat().st_size
    result_hero["image_sha256"] = sha256(output_image)
    write_json(DIST / "learning-home.json", result)
    if (DIST / "learning-home.json").stat().st_size > MAX_CATALOG_BYTES:
        fail("Generated learning-home.json exceeds 2 MiB")
    BUILD_STATS["home_slides"] += len(slides)

def build_books() -> None:
    source_path = CONTENT / "books" / "catalog.json"
    if not source_path.is_file():
        return
    source = require_dict(load_json(source_path), "book catalog")
    require_version(source.get("version"), "book catalog version")
    items = require_list(source.get("items"), "book catalog items")
    validate_catalog_ids(items, "book")
    result = copy.deepcopy(source)
    used_output_names: set[str] = set()

    for item in result.get("items", []):
        item_id = require_safe_id(item.get("id"), "book id")
        source_pdf_value = item.pop("source_pdf", "")
        source_cover_value = item.pop("source_cover", "")
        pdf_url = safe_asset_name(item.get("pdf_url"), f"pdf_url for {item_id}")
        cover_url = safe_asset_name(item.get("cover_url"), f"cover_url for {item_id}")
        if not pdf_url.lower().endswith(".pdf"):
            fail(f"Book pdf_url must end with .pdf: {pdf_url}")
        if Path(cover_url).suffix.lower() not in IMAGE_EXTENSIONS:
            fail(f"Book cover must be WebP, PNG, or JPEG: {cover_url}")
        require_version(item.get("pdf_version"), f"pdf_version for {item_id}")
        require_version(item.get("cover_version"), f"cover_version for {item_id}")
        page_count = require_version(item.get("page_count"), f"page_count for {item_id}")
        require_text(item.get("title"), f"book title for {item_id}", 260)

        for output_name in (pdf_url, cover_url):
            if output_name.lower() in used_output_names:
                fail(f"Duplicate book release asset name: {output_name}")
            used_output_names.add(output_name.lower())
            claim_asset(output_name, f"book release asset for {item_id}")

        source_pdf = source_file(source_pdf_value, "book PDF")
        source_cover = source_file(source_cover_value, "book cover")
        ensure_normal_file(source_pdf, "book PDF")
        ensure_normal_file(source_cover, "book cover")
        if source_pdf.stat().st_size <= 0:
            fail(f"Empty book PDF: {source_pdf}")
        if source_pdf.stat().st_size > MAX_BOOK_BYTES:
            fail(f"Book PDF exceeds 512 MiB: {source_pdf}")
        with source_pdf.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                fail(f"Invalid PDF header: {source_pdf}")

        output_pdf = DIST / pdf_url
        output_cover = DIST / cover_url
        shutil.copy2(source_pdf, output_pdf)
        shutil.copy2(source_cover, output_cover)
        item["pdf_sha256"] = sha256(output_pdf)
        item["pdf_size"] = output_pdf.stat().st_size
        item["page_count"] = page_count
        BUILD_STATS["books"] += 1

    write_json(DIST / "books-catalog.json", result)


def normalize_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (str, int, float)):
        text = str(value)
    else:
        return ""
    canonical = unicodedata.normalize("NFKC", text.strip()).casefold()
    return "".join(ch for ch in canonical
                   if not ch.isspace() and not unicodedata.category(ch).startswith("P"))


def answer_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    return ""


def validate_media_path(package_dir: Path, raw: Any, label: str,
                        allowed_extensions: set[str]) -> str:
    relative = safe_relative_path(raw, label)
    path = package_dir / relative
    ensure_normal_file(path, label)
    if path.stat().st_size <= 0:
        fail(f"Empty media file for {label}: {path}")
    if path.stat().st_size > MAX_PACKAGE_ENTRY_BYTES:
        fail(f"Media file is too large for {label}: {path}")
    if path.suffix.lower() not in allowed_extensions:
        fail(f"Unsupported media format for {label}: {relative}")
    return relative


def localized_required(obj: dict[str, Any], key: str, label: str, maximum: int) -> str:
    return require_text(obj.get(key), label, maximum)


def option_parts(option: Any, label: str) -> tuple[str, str, str]:
    if isinstance(option, dict):
        text = optional_text(option.get("text", option.get("value", "")), f"{label} text", 260)
        value = optional_text(option.get("value", text), f"{label} value", 260)
        image = optional_text(option.get("image", ""), f"{label} image", 512)
        if not value:
            fail(f"{label} value is empty")
        return text or value, value, image
    value = answer_to_text(option)
    if not value:
        fail(f"{label} is empty or unsupported")
    if len(value) > 260:
        fail(f"{label} is too long")
    return value, value, ""


def validate_exercise(package_dir: Path, exercise: dict[str, Any], lesson_id: str,
                      index: int) -> set[str]:
    exercise_id = require_safe_id(exercise.get("id"),
                                  f"exercise id in {lesson_id} at index {index}")
    exercise_type = require_text(exercise.get("type"), f"type for {exercise_id}", 40)
    if exercise_type == "pronunciation":
        fail(f"Repeat-after-me/pronunciation exercises are disabled in the learning path: {exercise_id}")
    if exercise_type not in SUPPORTED_EXERCISES:
        fail(f"Unsupported exercise type {exercise_type} in {lesson_id}/{exercise_id}")
    localized_required(exercise, "question", f"question for {exercise_id}", 1200)
    optional_text(exercise.get("question_en", ""), f"English question for {exercise_id}", 1200)
    optional_text(exercise.get("question_my", ""), f"Myanmar question for {exercise_id}", 1200)
    optional_text(exercise.get("hint", ""), f"hint for {exercise_id}", 1200)
    optional_text(exercise.get("explanation", ""), f"explanation for {exercise_id}", 1200)
    optional_text(exercise.get("pinyin", ""), f"pinyin for {exercise_id}", 260)

    referenced_media: set[str] = set()
    audio = optional_text(exercise.get("audio", ""), f"audio for {exercise_id}", 512)
    audio_text = optional_text(exercise.get("audio_text", exercise.get("text", "")),
                               f"audio_text for {exercise_id}", 260)
    if audio:
        referenced_media.add(validate_media_path(
            package_dir, audio, f"audio for {lesson_id}/{exercise_id}", AUDIO_EXTENSIONS))

    if exercise_type in {"single_choice", "listen_choice", "true_false", "image_choice"}:
        raw_options = exercise.get("options", [])
        if exercise_type == "true_false" and raw_options in (None, []):
            raw_options = ["true", "false"]
        options = require_list(raw_options, f"options for {exercise_id}", 2, MAX_OPTIONS)
        values: list[str] = []
        option_images = 0
        for option_index, option in enumerate(options):
            _, value, image = option_parts(option, f"option {option_index + 1} for {exercise_id}")
            key = normalize_key(value)
            if not key:
                fail(f"Choice option is empty for {exercise_id}")
            if key in {normalize_key(existing) for existing in values}:
                fail(f"Duplicate choice option in {exercise_id}: {value}")
            values.append(value)
            if image:
                referenced_media.add(validate_media_path(
                    package_dir, image, f"image option for {lesson_id}/{exercise_id}",
                    IMAGE_EXTENSIONS))
                option_images += 1

        answer = answer_to_text(exercise.get("answer"))
        if "answer_index" in exercise:
            answer_index = require_int(exercise.get("answer_index"),
                                       f"answer_index for {exercise_id}", 0, len(values) - 1)
            answer = values[answer_index]
        elif exercise_type == "true_false" and "answer_boolean" in exercise:
            if not isinstance(exercise.get("answer_boolean"), bool):
                fail(f"answer_boolean must be true or false for {exercise_id}")
            answer = "true" if exercise["answer_boolean"] else "false"
        if not answer:
            fail(f"Choice answer is empty for {exercise_id}")
        if normalize_key(answer) not in {normalize_key(value) for value in values}:
            fail(f"Choice answer is not present in options for {exercise_id}: {answer}")
        if exercise_type == "listen_choice" and not audio and not audio_text:
            fail(f"Listening exercise has no audio or audio_text: {exercise_id}")
        if exercise_type == "image_choice" and option_images == 0:
            fail(f"Image choice has no images: {exercise_id}")

    elif exercise_type in {"fill_blank", "dictation"}:
        answer = answer_to_text(exercise.get("answer"))
        if not normalize_key(answer):
            fail(f"Answer is empty for {exercise_id}")
        accepted = exercise.get("accepted_answers", [])
        if accepted is not None:
            accepted_values = require_list(accepted, f"accepted_answers for {exercise_id}",
                                           0, MAX_ACCEPTED_ANSWERS)
            for value in accepted_values:
                require_text(answer_to_text(value), f"accepted answer for {exercise_id}", 260)
        # A visible pinyin clue is important for Chinese typing questions.
        if not optional_text(exercise.get("pinyin", ""), f"pinyin for {exercise_id}", 260):
            fail(f"{exercise_type} requires a pinyin hint: {lesson_id}/{exercise_id}")
        if exercise_type == "dictation" and not audio and not audio_text:
            fail(f"Dictation has no audio or audio_text: {exercise_id}")

    elif exercise_type == "word_order":
        words = require_list(exercise.get("words"), f"words for {exercise_id}", 2, MAX_WORDS)
        word_values = [require_text(answer_to_text(word), f"word token for {exercise_id}", 260)
                       for word in words]
        answer = exercise.get("answer")
        if isinstance(answer, list):
            answer_values = [require_text(answer_to_text(word),
                                          f"answer token for {exercise_id}", 260)
                             for word in require_list(answer, f"answer for {exercise_id}", 2, MAX_WORDS)]
            if Counter(normalize_key(value) for value in word_values) != Counter(
                    normalize_key(value) for value in answer_values):
                fail(f"Word-order answer does not use the same tokens: {exercise_id}")
        else:
            answer_text = answer_to_text(answer)
            if not normalize_key(answer_text):
                fail(f"Word-order answer is empty: {exercise_id}")
            if normalize_key("".join(word_values)) != normalize_key(answer_text):
                fail(f"Word-order answer cannot be built from its word bank: {exercise_id}")

    elif exercise_type == "matching":
        pairs = require_list(exercise.get("pairs"), f"pairs for {exercise_id}", 2, MAX_PAIRS)
        left_seen: set[str] = set()
        right_seen: set[str] = set()
        for pair_index, pair in enumerate(pairs):
            pair = require_dict(pair, f"pair {pair_index + 1} for {exercise_id}")
            left = require_text(pair.get("left"), f"left pair value for {exercise_id}", 260)
            right = require_text(pair.get("right"), f"right pair value for {exercise_id}", 260)
            left_key, right_key = normalize_key(left), normalize_key(right)
            if left_key in left_seen or right_key in right_seen:
                fail(f"Matching pairs contain duplicate values: {exercise_id}")
            left_seen.add(left_key)
            right_seen.add(right_key)

    return referenced_media


def validate_lesson(package_dir: Path, lesson_file: Path, expected_lesson_id: str) -> tuple[int, set[str]]:
    ensure_normal_file(lesson_file, "lesson JSON")
    if lesson_file.stat().st_size > MAX_LESSON_BYTES:
        fail(f"Lesson JSON exceeds 2 MiB: {lesson_file}")
    lesson = require_dict(load_json(lesson_file), f"lesson {lesson_file}")
    schema = require_int(lesson.get("schema_version", 1),
                         f"schema_version in {lesson_file}", 1, 1)
    del schema
    lesson_id = require_safe_id(lesson.get("lesson_id"), f"lesson_id in {lesson_file}")
    if lesson_id != expected_lesson_id:
        fail(f"lesson_id mismatch in {lesson_file}: expected {expected_lesson_id}, got {lesson_id}")
    require_text(lesson.get("title"), f"title in {lesson_file}", 120)
    optional_text(lesson.get("subtitle", ""), f"subtitle in {lesson_file}", 360)
    if "passing_score" in lesson:
        require_int(lesson.get("passing_score"), f"passing_score in {lesson_file}", 0, 100)
    if "max_retries" in lesson:
        require_int(lesson.get("max_retries"), f"max_retries in {lesson_file}", 0, 5)
    exercises = require_list(lesson.get("exercises"), f"exercises in {lesson_file}",
                             1, MAX_EXERCISES)
    seen_ids: set[str] = set()
    media: set[str] = set()
    for index, raw_exercise in enumerate(exercises):
        exercise = require_dict(raw_exercise, f"exercise #{index + 1} in {lesson_file}")
        exercise_id = require_safe_id(exercise.get("id"),
                                      f"exercise id in {lesson_file} at index {index}")
        if exercise_id in seen_ids:
            fail(f"Duplicate exercise id {exercise_id} in {lesson_file}")
        seen_ids.add(exercise_id)
        media.update(validate_exercise(package_dir, exercise, lesson_id, index))
    return len(exercises), media


def scan_package_files(directory: Path) -> tuple[list[Path], int]:
    files: list[Path] = []
    total = 0
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            fail(f"Symlink is not allowed in learning package: {path}")
        if path.is_dir():
            continue
        ensure_normal_file(path, "learning package entry")
        relative = path.relative_to(directory).as_posix()
        safe_relative_path(relative, f"package entry {relative}")
        if path.stat().st_size > MAX_PACKAGE_ENTRY_BYTES:
            fail(f"Package entry exceeds 80 MiB: {path}")
        files.append(path)
        total += path.stat().st_size
        if len(files) > MAX_PACKAGE_ENTRIES:
            fail(f"Package has more than {MAX_PACKAGE_ENTRIES} files: {directory}")
        if total > MAX_UNPACKED_BYTES:
            fail(f"Package unpacked size exceeds 500 MiB: {directory}")
    if not files:
        fail(f"Empty learning package directory: {directory}")
    return files, total


def deterministic_zip(directory: Path, output: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as archive:
        for path in files:
            relative = path.relative_to(directory).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            with path.open("rb") as stream:
                archive.writestr(info, stream.read(), compress_type=zipfile.ZIP_DEFLATED,
                                 compresslevel=9)
    if output.stat().st_size <= 0 or output.stat().st_size > MAX_PACKAGE_BYTES:
        fail(f"Built package ZIP has invalid size: {output}")
    with zipfile.ZipFile(output, "r") as archive:
        bad = archive.testzip()
        if bad:
            fail(f"Corrupt ZIP entry after building {output.name}: {bad}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            fail(f"Duplicate ZIP entry names in {output.name}")


def deterministic_zip_json(output: Path, entry_name: str, value: Any) -> None:
    """Write one compact JSON entry with an ASCII-safe name into a deterministic ZIP."""
    safe_asset_name(entry_name, "ZIP entry name")
    try:
        entry_name.encode("ascii")
    except UnicodeEncodeError:
        fail(f"ZIP entry name must be ASCII: {entry_name}")
    payload = compact_json_bytes(value)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as archive:
        info = zipfile.ZipInfo(entry_name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (0o100644 & 0xFFFF) << 16
        archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    if output.stat().st_size <= 0 or output.stat().st_size > MAX_PACKAGE_BYTES:
        fail(f"Built package ZIP has invalid size: {output}")
    with zipfile.ZipFile(output, "r") as archive:
        bad = archive.testzip()
        if bad:
            fail(f"Corrupt ZIP entry after building {output.name}: {bad}")
        if archive.namelist() != [entry_name]:
            fail(f"Unexpected AI course ZIP layout: {output.name}")


def package_metadata() -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    packages_root = CONTENT / "packages"
    if not packages_root.is_dir():
        fail(f"Missing learning packages directory: {packages_root}")
    for directory in sorted(path for path in packages_root.iterdir() if path.is_dir()):
        if directory.is_symlink():
            fail(f"Package directory cannot be a symlink: {directory}")
        manifest_path = directory / "manifest.json"
        manifest = require_dict(load_json(manifest_path), f"manifest {manifest_path}")
        package_id = require_safe_id(manifest.get("package_id"), f"package_id in {manifest_path}")
        if directory.name != package_id:
            fail(f"Package directory name must equal package_id: {directory.name} != {package_id}")
        if package_id in packages:
            fail(f"Duplicate package_id: {package_id}")
        version = require_version(manifest.get("version"), f"package version in {manifest_path}")
        course_id = require_safe_id(manifest.get("course_id"), f"course_id in {manifest_path}")
        unit_id = require_safe_id(manifest.get("unit_id"), f"unit_id in {manifest_path}")
        files, unpacked_size = scan_package_files(directory)
        if manifest_path not in files:
            fail(f"Package manifest was not included: {manifest_path}")
        zip_name = claim_asset(f"{package_id}-v{version}.zip",
                               f"package asset for {package_id}")
        zip_path = DIST / zip_name
        deterministic_zip(directory, zip_path, files)
        packages[package_id] = {
            "version": version,
            "url": zip_name,
            "sha256": sha256(zip_path),
            "size": zip_path.stat().st_size,
            "unpacked_size": unpacked_size,
            "manifest": manifest,
            "directory": directory,
            "course_id": course_id,
            "unit_id": unit_id,
            "source_files": {path.relative_to(directory).as_posix() for path in files},
            "referenced_lessons": set(),
            "referenced_media": set(),
        }
        BUILD_STATS["learning_packages"] += 1
    return packages


def validate_catalog_title(obj: dict[str, Any], label: str) -> None:
    require_text(obj.get("title"), f"{label} title", 120)
    optional_text(obj.get("title_en", ""), f"{label} English title", 120)
    optional_text(obj.get("title_my", ""), f"{label} Myanmar title", 120)
    optional_text(obj.get("subtitle", ""), f"{label} subtitle", 360)
    optional_text(obj.get("subtitle_en", ""), f"{label} English subtitle", 360)
    optional_text(obj.get("subtitle_my", ""), f"{label} Myanmar subtitle", 360)


def build_learning_path(packages: dict[str, dict[str, Any]]) -> None:
    catalog_path = CONTENT / "learning_path" / "catalog.json"
    catalog = require_dict(load_json(catalog_path), "learning path catalog")
    if catalog_path.stat().st_size > MAX_CATALOG_BYTES:
        fail(f"Learning path source catalog exceeds 2 MiB: {catalog_path}")
    require_int(catalog.get("schema_version", 1), "learning path schema_version", 1, 1)
    require_version(catalog.get("version"), "learning path catalog version")
    updated_at = require_text(catalog.get("updated_at"), "learning path updated_at", 80)
    if not UPDATED_AT.fullmatch(updated_at):
        fail(f"learning path updated_at must be UTC like 2026-08-05T16:35:00Z: {updated_at}")
    courses = require_list(catalog.get("courses"), "learning path courses", 1, MAX_COURSES)

    seen_course_ids: set[str] = set()
    global_package_descriptors: dict[str, tuple[int, str, str, int]] = {}
    for course_index, course_raw in enumerate(courses):
        course = require_dict(course_raw, f"course #{course_index + 1}")
        course_id = require_safe_id(course.get("id"), f"course #{course_index + 1} id")
        if course_id in seen_course_ids:
            fail(f"Duplicate course id: {course_id}")
        seen_course_ids.add(course_id)
        validate_catalog_title(course, f"course {course_id}")
        require_version(course.get("version"), f"version for course {course_id}")
        require_int(course.get("min_app_version", 0), f"min_app_version for {course_id}",
                    0, 2_147_483_647)
        accent = optional_text(course.get("accent", ""), f"accent for {course_id}", 16)
        if accent and not HEX_COLOR.fullmatch(accent):
            fail(f"Invalid course accent color for {course_id}: {accent}")
        units = require_list(course.get("units"), f"units for {course_id}",
                             1, MAX_UNITS_PER_COURSE)
        seen_unit_ids: set[str] = set()
        seen_orders: set[int] = set()
        seen_lesson_ids: set[str] = set()
        earlier_lessons: set[str] = set()
        lesson_count = 0

        for unit_index, unit_raw in enumerate(units):
            unit = require_dict(unit_raw, f"unit #{unit_index + 1} in {course_id}")
            unit_id = require_safe_id(unit.get("id"), f"unit id in {course_id}")
            if unit_id in seen_unit_ids:
                fail(f"Duplicate unit id in {course_id}: {unit_id}")
            seen_unit_ids.add(unit_id)
            order = require_int(unit.get("order", unit_index), f"order for unit {unit_id}",
                                -1_000_000, 1_000_000)
            if order in seen_orders:
                fail(f"Duplicate unit order in {course_id}: {order}")
            seen_orders.add(order)
            validate_catalog_title(unit, f"unit {unit_id}")
            accent = optional_text(unit.get("accent", ""), f"accent for unit {unit_id}", 16)
            if accent and not HEX_COLOR.fullmatch(accent):
                fail(f"Invalid unit accent color for {unit_id}: {accent}")
            lessons = require_list(unit.get("lessons"), f"lessons for unit {unit_id}", 1)
            BUILD_STATS["units"] += 1

            for lesson_index, lesson_raw in enumerate(lessons):
                lesson = require_dict(lesson_raw, f"lesson #{lesson_index + 1} in {unit_id}")
                lesson_id = require_safe_id(lesson.get("id"), f"lesson id in unit {unit_id}")
                if lesson_id in seen_lesson_ids:
                    fail(f"Duplicate lesson id in course {course_id}: {lesson_id}")
                seen_lesson_ids.add(lesson_id)
                lesson_count += 1
                if lesson_count > MAX_LESSONS_PER_COURSE:
                    fail(f"Course has more than {MAX_LESSONS_PER_COURSE} lessons: {course_id}")
                validate_catalog_title(lesson, f"lesson {lesson_id}")
                lesson_type = optional_text(lesson.get("type", "normal"),
                                            f"type for lesson {lesson_id}", 32) or "normal"
                if lesson_type not in ALLOWED_LESSON_TYPES:
                    fail(f"Unsupported map lesson type for {lesson_id}: {lesson_type}")
                position = optional_text(lesson.get("position", "center"),
                                         f"position for {lesson_id}", 16) or "center"
                if position not in ALLOWED_POSITIONS:
                    fail(f"Invalid map position for {lesson_id}: {position}")
                require_int(lesson.get("exercise_count", 8),
                            f"exercise_count for {lesson_id}", 1, 200)
                require_int(lesson.get("minutes", 4), f"minutes for {lesson_id}", 1, 240)
                requirements = require_list(lesson.get("required_lessons", []),
                                            f"required_lessons for {lesson_id}", 0,
                                            MAX_REQUIREMENTS)
                requirement_ids: list[str] = []
                for requirement in requirements:
                    requirement_id = require_safe_id(requirement,
                                                     f"required lesson for {lesson_id}")
                    if requirement_id in requirement_ids:
                        fail(f"Duplicate required lesson {requirement_id} for {lesson_id}")
                    if requirement_id == lesson_id:
                        fail(f"Lesson cannot require itself: {lesson_id}")
                    if requirement_id not in earlier_lessons:
                        fail(f"Required lesson must exist earlier: {requirement_id} -> {lesson_id}")
                    requirement_ids.append(requirement_id)

                if lesson_type == "trophy":
                    if lesson.get("package_id") or lesson.get("lesson_file"):
                        warn(f"Trophy {lesson_id} contains unused package fields")
                    earlier_lessons.add(lesson_id)
                    BUILD_STATS["lessons"] += 1
                    continue

                package_id = require_safe_id(lesson.get("package_id"),
                                             f"package_id for lesson {lesson_id}")
                meta = packages.get(package_id)
                if not meta:
                    fail(f"Lesson {lesson_id} references missing package {package_id}")
                if meta["course_id"] != course_id or meta["unit_id"] != unit_id:
                    fail(f"Package {package_id} course/unit does not match {course_id}/{unit_id}")
                package_version = require_version(lesson.get("package_version"),
                                                  f"package_version for {lesson_id}")
                if package_version != meta["version"]:
                    fail(f"Package version mismatch for {lesson_id}: catalog={package_version}, "
                         f"manifest={meta['version']}")
                lesson_file = safe_relative_path(lesson.get("lesson_file"),
                                                 f"lesson_file for {lesson_id}")
                if not lesson_file.startswith("lessons/") or not lesson_file.endswith(".json"):
                    fail(f"lesson_file must be lessons/*.json for {lesson_id}: {lesson_file}")
                source_lesson = meta["directory"] / lesson_file
                if not source_lesson.is_file():
                    fail(f"Missing lesson file: {source_lesson}")
                exercise_count, media = validate_lesson(meta["directory"], source_lesson, lesson_id)
                declared_count = require_int(lesson.get("exercise_count"),
                                             f"exercise_count for {lesson_id}", 1, 200)
                if declared_count != exercise_count:
                    fail(f"exercise_count mismatch for {lesson_id}: catalog={declared_count}, "
                         f"lesson={exercise_count}")
                meta["referenced_lessons"].add(lesson_file)
                meta["referenced_media"].update(media)
                descriptor = (meta["version"], meta["url"], meta["sha256"], meta["size"])
                previous = global_package_descriptors.get(package_id)
                if previous is not None and previous != descriptor:
                    fail(f"Conflicting package metadata for {package_id}")
                global_package_descriptors[package_id] = descriptor
                lesson["package_url"] = meta["url"]
                lesson["package_sha256"] = meta["sha256"]
                lesson["package_size"] = meta["size"]
                earlier_lessons.add(lesson_id)
                BUILD_STATS["lessons"] += 1
                BUILD_STATS["exercises"] += exercise_count

        BUILD_STATS["courses"] += 1

    # Report old source lessons that are no longer reachable. They are harmless because the App can
    # only open catalog entries, but deleting them keeps Release packages small and unambiguous.
    for package_id, meta in packages.items():
        source_lessons = {
            name for name in meta["source_files"]
            if name.startswith("lessons/") and name.endswith(".json")
        }
        orphaned = sorted(source_lessons - meta["referenced_lessons"])
        if orphaned:
            warn(f"Package {package_id} contains unreferenced lesson JSON; remove when convenient: "
                 + ", ".join(orphaned))
        if not meta["referenced_lessons"]:
            fail(f"Package {package_id} is not referenced by the learning catalog")

    output = DIST / "learning-path-catalog.json"
    write_json(output, catalog)
    if output.stat().st_size > MAX_CATALOG_BYTES:
        fail(f"Generated learning-path-catalog.json exceeds 2 MiB")



def _contains_myanmar(text: str) -> bool:
    return any("\u1000" <= ch <= "\u109f" or "\uaa60" <= ch <= "\uaa7f" for ch in text)


def build_ai_course() -> None:
    """Build a total AI course catalog and 60 independently downloadable category ZIPs.

    Git source filenames use Chinese + pinyin for maintainers. Release asset names and ZIP
    internal entry names are ASCII-only to avoid URL/ZIP filename mojibake on Android/Windows.
    The total catalog contains 12 parts, 60 categories, and all 240 second-level scene titles.
    """
    root = CONTENT / "ai_course"
    catalog_path = root / "总目录_zong_mulu.json"
    if not catalog_path.is_file():
        return

    source = require_dict(load_json(catalog_path), "AI course total catalog")
    require_version(source.get("v"), "AI course catalog version")
    catalog_title = require_text(source.get("title"), "AI course catalog Myanmar title", 180)
    if not _contains_myanmar(catalog_title):
        fail("AI course catalog title must contain Myanmar script")
    require_text(source.get("zh"), "AI course catalog Chinese note", 160)

    parts = require_list(source.get("parts"), "AI course catalog parts", 1, 20)
    items = require_list(source.get("items"), "AI course catalog items", 1, 100)
    if len(items) != 60:
        fail(f"AI course catalog must contain 60 categories, got {len(items)}")

    part_item_ids: list[str] = []
    seen_part_ids: set[str] = set()
    for index, part_raw in enumerate(parts, start=1):
        part = require_dict(part_raw, f"AI course part #{index}")
        part_id = require_text(part.get("id"), f"AI course part id #{index}", 8)
        if part_id in seen_part_ids:
            fail(f"Duplicate AI course part id: {part_id}")
        seen_part_ids.add(part_id)
        title_my = require_text(part.get("title"), f"Myanmar title for part {part_id}", 180)
        if not _contains_myanmar(title_my):
            fail(f"AI course part title must contain Myanmar script: {part_id}")
        require_text(part.get("zh"), f"Chinese note for part {part_id}", 120)
        ids = require_list(part.get("items"), f"category ids in part {part_id}", 1, 20)
        for item_id in ids:
            part_item_ids.append(require_text(item_id, f"category id in part {part_id}", 8))

    result = copy.deepcopy(source)
    seen_ids: set[str] = set()
    used_assets: set[str] = set()
    category_ids: list[str] = []

    for index, item in enumerate(result.get("items", []), start=1):
        item = require_dict(item, "AI course catalog item")
        item_id = require_text(item.get("id"), f"AI course item id #{index}", 8)
        expected_id = f"{index:02d}"
        if item_id != expected_id:
            fail(f"AI course id/order mismatch: expected {expected_id}, got {item_id}")
        if item_id in seen_ids:
            fail(f"Duplicate AI course item id: {item_id}")
        seen_ids.add(item_id)
        category_ids.append(item_id)

        title_my = require_text(item.get("title"), f"Myanmar title for {item_id}", 180)
        if not _contains_myanmar(title_my):
            fail(f"AI course title must contain Myanmar script: {item_id}")
        title_zh = require_text(item.get("zh"), f"Chinese note for {item_id}", 120)
        version = require_version(item.get("v"), f"AI course version for {item_id}")

        source_value = item.pop("file", "")
        source_data = source_file(source_value, f"AI course source for {item_id}")
        ensure_normal_file(source_data, "AI course category JSON")
        if source_data.suffix.lower() != ".json":
            fail(f"AI course source must be JSON: {source_data}")
        expected_prefix = f"{item_id}_{title_zh}_"
        if not source_data.name.startswith(expected_prefix):
            fail(f"AI course source filename must start with Chinese title + pinyin: {source_data.name}")

        category = require_dict(load_json(source_data), f"AI course category {source_data.name}")
        if require_version(category.get("v"), f"v in {source_data.name}") != version:
            fail(f"AI course version mismatch: {item_id}")
        if require_text(category.get("id"), f"id in {source_data.name}", 8) != item_id:
            fail(f"AI course category id mismatch: {source_data.name}")
        if require_text(category.get("title"), f"title in {source_data.name}", 180) != title_my:
            fail(f"AI course Myanmar title mismatch: {source_data.name}")
        if require_text(category.get("zh"), f"zh in {source_data.name}", 120) != title_zh:
            fail(f"AI course Chinese title mismatch: {source_data.name}")

        scenes = require_list(category.get("scenes"), f"scenes in {source_data.name}", 1, 12)
        summary_scenes = require_list(item.get("scenes"), f"scene summaries for {item_id}", 1, 12)
        if len(summary_scenes) != len(scenes):
            fail(f"Scene summary count mismatch for {item_id}")

        scene_ids: set[str] = set()
        for scene_index, scene_raw in enumerate(scenes, start=1):
            scene = require_dict(scene_raw, f"scene #{scene_index} in {source_data.name}")
            scene_id = require_text(scene.get("id"), f"scene id in {source_data.name}", 12)
            expected_scene_id = f"{item_id}.{scene_index}"
            if scene_id != expected_scene_id:
                fail(f"Scene id/order mismatch: expected {expected_scene_id}, got {scene_id}")
            if scene_id in scene_ids:
                fail(f"Duplicate scene id: {scene_id}")
            scene_ids.add(scene_id)
            scene_title = require_text(scene.get("title"), f"Myanmar scene title {scene_id}", 180)
            if not _contains_myanmar(scene_title):
                fail(f"Scene title must contain Myanmar script: {scene_id}")
            scene_zh = require_text(scene.get("zh"), f"Chinese scene note {scene_id}", 120)
            require_text(scene.get("teach"), f"teach {scene_id}", 1800)
            say = require_list(scene.get("say"), f"say {scene_id}", 1, 16)
            listen = require_list(scene.get("listen"), f"listen {scene_id}", 1, 20)
            for line in say:
                require_text(line, f"say line {scene_id}", 260)
            for line in listen:
                require_text(line, f"listen line {scene_id}", 260)
            require_text(scene.get("variants"), f"variants {scene_id}", 1800)

            functions = require_list(scene.get("functions"), f"functions {scene_id}", 2, 4)
            seen_functions: set[str] = set()
            for function in functions:
                name = require_text(function, f"function {scene_id}", 80)
                if name in seen_functions:
                    fail(f"Duplicate AI course function in {scene_id}: {name}")
                seen_functions.add(name)

            patterns = require_list(scene.get("patterns"), f"patterns {scene_id}", 1, 3)
            for pattern_index, pattern_raw in enumerate(patterns, start=1):
                pattern = require_dict(pattern_raw, f"pattern #{pattern_index} in {scene_id}")
                require_text(pattern.get("zh"), f"pattern label {scene_id} #{pattern_index}", 80)
                require_text(pattern.get("form"), f"pattern form {scene_id} #{pattern_index}", 600)
                require_text(pattern.get("ex"), f"pattern example {scene_id} #{pattern_index}", 260)

            grammar = scene.get("grammar", [])
            if grammar is not None:
                for grammar_index, grammar_raw in enumerate(
                        require_list(grammar, f"grammar {scene_id}", 0, 2), start=1):
                    point = require_dict(grammar_raw, f"grammar #{grammar_index} in {scene_id}")
                    require_text(point.get("point"), f"grammar point {scene_id} #{grammar_index}", 100)
                    require_text(point.get("note"), f"grammar note {scene_id} #{grammar_index}", 500)

            events = require_list(scene.get("events"), f"events {scene_id}", 2, 4)
            seen_events: set[str] = set()
            for event in events:
                text = require_text(event, f"event {scene_id}", 600)
                if text in seen_events:
                    fail(f"Duplicate AI course event in {scene_id}: {text}")
                seen_events.add(text)

            optional_text(scene.get("safety", ""), f"safety {scene_id}", 800)
            require_text(scene.get("roles"), f"roles {scene_id}", 600)
            require_text(scene.get("task"), f"task {scene_id}", 1200)

            summary = require_dict(summary_scenes[scene_index - 1], f"scene summary {scene_id}")
            if require_text(summary.get("id"), f"summary id {scene_id}", 12) != scene_id:
                fail(f"Scene summary id mismatch: {scene_id}")
            if require_text(summary.get("title"), f"summary title {scene_id}", 180) != scene_title:
                fail(f"Scene summary Myanmar title mismatch: {scene_id}")
            if require_text(summary.get("zh"), f"summary zh {scene_id}", 120) != scene_zh:
                fail(f"Scene summary Chinese title mismatch: {scene_id}")

        data_url = safe_asset_name(item.get("zip"), f"AI course ZIP for {item_id}")
        try:
            data_url.encode("ascii")
        except UnicodeEncodeError:
            fail(f"AI course release ZIP name must be ASCII: {data_url}")
        if data_url.lower() in used_assets:
            fail(f"Duplicate AI course ZIP name: {data_url}")
        used_assets.add(data_url.lower())
        claim_asset(data_url, f"AI course release asset for {item_id}")
        zip_path = DIST / data_url
        deterministic_zip_json(zip_path, "content.json", category)
        item["entry"] = "content.json"
        item["sha256"] = sha256(zip_path)
        item["size"] = zip_path.stat().st_size
        item["count"] = len(scenes)
        BUILD_STATS["ai_course_categories"] += 1
        BUILD_STATS["ai_course_scenes"] += len(scenes)

    if sorted(part_item_ids) != sorted(category_ids) or len(part_item_ids) != len(category_ids):
        fail("AI course parts must cover all 60 categories exactly once")
    if BUILD_STATS["ai_course_scenes"] != 240:
        fail(f"AI course must contain 240 scenes, got {BUILD_STATS['ai_course_scenes']}")

    rules_source = root / "教学规则_jiaoxue_guize.json"
    rules = require_dict(load_json(rules_source), "AI course teaching rules")
    rules_version = require_version(rules.get("v"), "AI course rules version")
    rules_title = require_text(rules.get("title"), "AI course rules Myanmar title", 180)
    if not _contains_myanmar(rules_title):
        fail("AI course rules title must contain Myanmar script")
    require_text(rules.get("zh"), "AI course rules Chinese note", 120)
    require_list(rules.get("rules"), "AI course rules", 1, 32)
    require_list(rules.get("flow"), "AI course teaching flow", 1, 16)
    require_list(rules.get("survival"), "AI course survival phrases", 1, 32)
    rules_name = claim_asset(f"ai_course_rules_v{rules_version}.json", "AI course rules asset")
    rules_output = DIST / rules_name
    shutil.copy2(rules_source, rules_output)
    result["rules"] = {
        "v": rules_version,
        "url": rules_name,
        "sha256": sha256(rules_output),
        "size": rules_output.stat().st_size,
    }

    write_json(DIST / "ai-course-catalog.json", result)


def build_metadata() -> None:
    metadata = {
        "schema_version": 1,
        "release_version": os.environ.get("RELEASE_VERSION", "local-test"),
        "counts": dict(BUILD_STATS),
        "assets": [],
    }
    # Do not include content-metadata.json in its own asset list.
    for path in sorted(path for path in DIST.iterdir()
                       if path.is_file() and path.name != "content-metadata.json"):
        metadata["assets"].append({
            "name": path.name,
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    write_json(DIST / "content-metadata.json", metadata)


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    build_words()
    build_speaking()
    build_patterns()
    build_home()
    build_books()
    build_ai_course()
    packages = package_metadata()
    build_learning_path(packages)
    build_metadata()

    print("Build succeeded. Content counts:")
    for key, value in BUILD_STATS.items():
        print(f"  {key}: {value}")
    print("Release assets:")
    for path in sorted(DIST.iterdir()):
        print(f"  {path.name} ({path.stat().st_size} bytes, sha256={sha256(path)})")


if __name__ == "__main__":
    main()
