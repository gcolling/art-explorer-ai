
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


COLUMN_MAP = {
    "Object ID": "object_id",
    "Object Number": "object_number",
    "Title": "title",
    "Object Name": "object_name",
    "Department": "department",
    "Classification": "classification",
    "Artist Display Name": "artist_name",
    "Artist Role": "artist_role",
    "Artist Display Bio": "artist_bio",
    "Artist Nationality": "artist_nationality",
    "Artist Begin Date": "artist_begin_date",
    "Artist End Date": "artist_end_date",
    "Culture": "culture",
    "Period": "period",
    "Dynasty": "dynasty",
    "Reign": "reign",
    "Object Date": "object_date",
    "Object Begin Date": "object_begin_date",
    "Object End Date": "object_end_date",
    "Medium": "medium",
    "Dimensions": "dimensions",
    "Geography Type": "geography_type",
    "City": "city",
    "Country": "country",
    "Region": "region",
    "Is Public Domain": "is_public_domain",
    "Is Highlight": "is_highlight",
    "Tags": "tags",
    "Link Resource": "met_url",
    "Object Wikidata URL": "object_wikidata_url",
    "Artist Wikidata URL": "artist_wikidata_url",
    "Credit Line": "credit_line",
    "Rights and Reproduction": "rights_and_reproduction",
}

BOOLEAN_COLUMNS = {"is_public_domain", "is_highlight"}

INTEGER_COLUMNS = {
    "object_id",
    "artist_begin_date",
    "artist_end_date",
    "object_begin_date",
    "object_end_date",
}


def rx(pattern):
    return re.compile(pattern, re.IGNORECASE)

ART_FORMS = [
    ("painting", rx(r"\b(?:paintings?|fresco(?:es|s)?|wall paintings?|miniature paintings?)\b")),
    ("drawing", rx(r"\b(?:drawings?|watercolou?rs?|pastels?|sketch(?:es|books)?)\b")),
    ("print", rx(r"\b(?:prints?|woodcuts?|woodblock prints?|lithograph(?:s|y)?|etchings?|engravings?|screenprints?|mezzotints?|aquatints?)\b")),
    ("photography", rx(r"\b(?:photograph(?:s|y|ic)?|daguerreotypes?|cyanotypes?|stereographs?|autochromes?|photogravures?)\b")),
    ("sculpture", rx(r"\b(?:sculptures?|statues?|statuettes?|figurines?|busts?|reliefs?|maquettes?|sculptural groups?)\b")),
    ("manuscripts_books", rx(r"\b(?:illuminated manuscripts?|illuminated folios?|calligraphy|calligraphic works?)\b")),
    ("architectural_art", rx(r"\b(?:mosaics?|stained glass(?: windows?| panels?)?)\b")),
    ("contemporary_media", rx(r"\b(?:video art|digital art|performance art|art installations?|moving images?|variable media)\b")),
    ("design_commercial_art", rx(r"\b(?:posters?|graphic designs?|advertising posters?)\b")),
    ("textiles", rx(r"\b(?:tapestr(?:y|ies)|pictorial embroider(?:y|ies)|embroidered panels?|art quilts?)\b")),
]

FUNCTIONAL = rx(
    r"\b(?:armchairs?|chairs?|sofas?|stools?|benches?|tables?|desks?|cabinets?|"
    r"beds?|dress(?:es)?|skirts?|coats?|robes?|shoes?|boots?|hats?|gloves?|"
    r"fans?|watches?|clocks?|lamps?|candlesticks?|chandeliers?|"
    r"spoons?|forks?|knives?|cutlery|plates?|bowls?|cups?|saucers?|"
    r"jars?|pitchers?|teapots?|vases?|bottles?|snuff bottles?|"
    r"weapons?|swords?|daggers?|firearms?|helmets?|shields?|armor|armour|"
    r"coins?|currency|tokens?|seals?|sealings?|tools?|implements?|"
    r"buttons?|buckles?|keys?|locks?|combs?|containers?|"
    r"netsuke|inrō|inro|ornaments?|jewel(?:ry|lery)|necklaces?|"
    r"bracelets?|earrings?|rings?|brooch(?:es)?|pendants?)\b"
)

FIGURAL = rx(r"\b(?:figures?|figurines?|statuettes?|statues?|busts?)\b")

def classify_object(row):
    """Return the artwork category, or None when outside our conservative scope."""
    classification = row.get("classification") or ""
    object_name = row.get("object_name") or ""

    if FUNCTIONAL.search(object_name):
        return None

    for category, pattern in ART_FORMS:
        if pattern.search(object_name):
            return category

    if FIGURAL.search(object_name):
        return "sculpture"

    for category, pattern in ART_FORMS:
        if pattern.search(classification):
            return category

    return None


def clean_text(value):
    if pd.isna(value):
        return None

    value = str(value).strip()
    value = re.sub(r"\s+", " ", value)

    return value if value else None


def clean_integer(value):
    if pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    try:
        number = float(value)
        return int(number) if number.is_integer() else None
    except (ValueError, OverflowError):
        return None


def clean_boolean(value):
    if pd.isna(value):
        return None

    normalized = str(value).strip().lower()

    if normalized in {"true", "1", "yes"}:
        return True

    if normalized in {"false", "0", "no"}:
        return False

    return None


def parse_tags(value):
    if pd.isna(value):
        return []

    tags = []
    seen = set()

    for part in str(value).split("|"):
        tag = clean_text(part)

        if tag and tag.casefold() not in seen:
            tags.append(tag)
            seen.add(tag.casefold())

    return tags


def clean_record(row):
    result = {}

    for source_name, target_name in COLUMN_MAP.items():
        value = row.get(source_name)

        if target_name == "tags":
            result[target_name] = parse_tags(value)

        elif target_name in BOOLEAN_COLUMNS:
            result[target_name] = clean_boolean(value)

        elif target_name in INTEGER_COLUMNS:
            result[target_name] = clean_integer(value)

        else:
            result[target_name] = clean_text(value)

    category = classify_object(result)
    result["category"] = category
    result["image_url"] = None
    result["image_small_url"] = None
    result["has_image"] = None

    return result


def write_jsonl(handle, record):
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def process_dataset(input_path, output_dir, chunk_size):
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "artworks.jsonl"
    source_rows = 0
    public_domain_skipped = 0
    outside_scope_skipped = 0
    missing_id_skipped = 0
    duplicate_skipped = 0
    included = 0
    seen_ids = set()

    reader = pd.read_csv(
        input_path, dtype=str, chunksize=chunk_size,
        keep_default_na=False, na_values=[""],
        encoding="utf-8-sig", on_bad_lines="error",
    )

    with output_path.open("w", encoding="utf-8") as output:
        for chunk_number, chunk in enumerate(reader, start=1):
            if chunk_number == 1:
                required = {"Object ID", "Is Public Domain"}
                missing = required - set(chunk.columns)
                if missing:
                    raise ValueError(f"Missing required columns: {sorted(missing)}")

            source_rows += len(chunk)
            mask = chunk["Is Public Domain"].str.strip().str.casefold().eq("true")
            public_domain_skipped += int((~mask).sum())

            for row in chunk.loc[mask].to_dict(orient="records"):
                record = clean_record(row)
                object_id = record["object_id"]
                if object_id is None:
                    missing_id_skipped += 1
                    continue
                if object_id in seen_ids:
                    duplicate_skipped += 1
                    continue
                seen_ids.add(object_id)

                if record["category"] is None:
                    outside_scope_skipped += 1
                    continue

                write_jsonl(output, record)
                included += 1

            print(f"Processed chunk {chunk_number} ({source_rows:,} source rows)")

    print(f"\nArtworks written: {included:,}")
    print(f"Public-domain filter skipped: {public_domain_skipped:,}")
    print(f"Outside artwork scope skipped: {outside_scope_skipped:,}")
    print(f"Missing IDs skipped: {missing_id_skipped:,}")
    print(f"Duplicate IDs skipped: {duplicate_skipped:,}")
    print(f"Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Select public-domain artworks from The Met CSV.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    parser.add_argument("--chunk-size", type=int, default=10000)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")
    if args.chunk_size < 1:
        parser.error("--chunk-size must be at least 1")
    process_dataset(args.input, args.output, args.chunk_size)


if __name__ == "__main__":
    main()
