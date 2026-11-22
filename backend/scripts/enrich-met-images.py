import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx


PROCESSED_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
INPUT_PATH = PROCESSED_DATA_DIR / "artworks.jsonl"
OUTPUT_PATH = PROCESSED_DATA_DIR / "artworks_with_images.jsonl"
MET_API_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/"
TRUSTED_IMAGE_HOST = "images.metmuseum.org"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_trusted_met_image_url(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname == TRUSTED_IMAGE_HOST
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and bool(parsed.path)
        )
    except ValueError:
        return False


def extract_image_urls(record, object_id):
    if not isinstance(record, dict):
        return None
    if record.get("objectID") != object_id or record.get("isPublicDomain") is not True:
        return None

    full = record.get("primaryImage")
    small = record.get("primaryImageSmall")
    full = full if is_trusted_met_image_url(full) else None
    small = small if is_trusted_met_image_url(small) else None

    if not full and not small:
        return None
    return full or small, small or full


def fetch_met_object(client, object_id, max_attempts, delay):
    url = f"{MET_API_URL}{object_id}"
    for attempt in range(max_attempts):
        try:
            response = client.get(url)
            if response.status_code != 200:
                print(f"Artwork {object_id}: HTTP {response.status_code}")
            if response.status_code == 200:
                try:
                    return "ok", response.json()
                except ValueError:
                    return "failed", None
            if response.status_code == 404:
                return "not_found", None
            if response.status_code not in RETRYABLE_STATUS_CODES:
                return "failed", None
            retry_after = response.headers.get("Retry-After")
            try:
                wait = max(0.0, min(float(retry_after), 60.0)) if retry_after else None
            except ValueError:
                wait = None
        except httpx.RequestError as exc:
            print(f"Artwork {object_id}: {type(exc).__name__}: {exc}")
            wait = None

        if attempt + 1 < max_attempts:
            time.sleep(wait if wait is not None else delay * (2 ** attempt))

    return "failed", None


def load_completed_ids(output_path):
    completed = set()
    if not output_path.exists():
        return completed
    with output_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {output_path}:{line_number}") from exc
            object_id = record.get("object_id")
            if isinstance(object_id, int) and not isinstance(object_id, bool):
                completed.add(object_id)
    return completed


def process_artwork(input_path, output_path, limit, delay, max_attempts):
    completed = load_completed_ids(output_path)
    attempted = 0
    enriched = 0
    without_images = 0
    not_found = 0
    failed = 0
    skipped_completed = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        input_path.open("r", encoding="utf-8") as input_file,
        output_path.open("a", encoding="utf-8") as output_file,
        httpx.Client(
            timeout=10.0,
            follow_redirects=False,
            headers={"User-Agent": "ArtExplorer/1.0", "Accept": "application/json"},
        ) as client,
    ):
        for line_number, line in enumerate(input_file, 1):
            if not line.strip():
                continue
            if limit is not None and attempted >= limit:
                break
            try:
                artwork = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {input_path}:{line_number}") from exc
            object_id = artwork.get("object_id")
            if not isinstance(object_id, int) or isinstance(object_id, bool) or object_id <= 0:
                failed += 1
                continue
            if object_id in completed:
                skipped_completed += 1
                continue

            attempted += 1
            status, record = fetch_met_object(client, object_id, max_attempts, delay)
            if status == "failed":
                failed += 1
                print(f"API request failed for artwork {object_id}; will retry next run")
            elif status == "not_found":
                not_found += 1
                print(f"Artwork {object_id} not found")
            else:
                urls = extract_image_urls(record, object_id)
                if urls is None:
                    without_images += 1
                    print(f"Artwork {object_id} has no usable image")
                else:
                    artwork["image_url"], artwork["image_small_url"] = urls
                    artwork["has_image"] = True
                    output_file.write(json.dumps(artwork, ensure_ascii=False) + "\n")
                    output_file.flush()
                    enriched += 1
                    completed.add(object_id)

            if attempted % 100 == 0:
                print(f"Processed {attempted} new artworks; {enriched} with images")
            if delay > 0:
                time.sleep(delay)

    print(f"Attempted: {attempted}")
    print(f"With images: {enriched}")
    print(f"Without usable images: {without_images}")
    print(f"Not found: {not_found}")
    print(f"Failed (retry next run): {failed}")
    print(f"Previously completed (skipped): {skipped_completed}")
    print(f"Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Enrich Met artworks with trusted image URLs")
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.6)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be zero or greater")
    if args.delay < 0:
        parser.error("--delay must be zero or greater")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output paths must be different")

    process_artwork(args.input, args.output, args.limit, args.delay, args.max_attempts)


if __name__ == "__main__":
    main()
