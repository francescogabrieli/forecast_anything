"""Reproducible public-data recipes; manifests use the JSON subset of YAML.

No spreadsheet, HTTP, or YAML dependency is required by the forecasting core.
Raw downloads and preparation locks belong in ignored local directories.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from zipfile import ZipFile

from forecast_anything.providers.base import frequency_step

USER_AGENT = "ForecastAnythingBenchmark/0.1 (research; https://github.com/francescogabrieli/forecast_anything)"
FIELDS = ("series_id", "event_time", "available_at", "revision", "value", "unit")
M5_SOURCE_FILES = (
    "calendar.csv",
    "sales_train_validation.csv",
    "sales_train_evaluation.csv",
    "sales_test_validation.csv",
    "sales_test_evaluation.csv",
    "sell_prices.csv",
)
M5_SERIES_FILES = ("calendar.csv", "sales_train_validation.csv")


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    if manifest.get("version") != 1:
        raise ValueError("unsupported benchmark manifest version")
    return manifest


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("benchmark timestamps require an explicit timezone")
    return parsed.astimezone(UTC)


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def bucket_calendar(config):
    start, end = timestamp(config["start"]), timestamp(config["end"])
    step = frequency_step(config["frequency"])
    if end < start or (end - start) % step:
        raise ValueError("invalid benchmark coverage")
    return tuple(start + step * i for i in range((end - start) // step + 1))


def _raw(manifest, config, destination, name, source=None):
    source = source or config["source"]
    source_identity = source.get("url", f"file:{source.get('path', '')}")
    source_key = hashlib.sha256(source_identity.encode()).hexdigest()[:16]
    raw_name = source_key if source.get("shared_cache") else f"{name}.{source_key}"
    raw = destination / "raw" / f"{raw_name}.download"
    raw.parent.mkdir(parents=True, exist_ok=True)
    if "path" in source:
        shutil.copyfile(manifest.parent / source["path"], raw)
    elif not raw.exists():
        request = urllib.request.Request(
            source["url"], headers={"User-Agent": USER_AGENT}
        )
        partial = raw.with_suffix(".partial")
        try:
            # Sequential by construction: no Wikimedia request fan-out.
            with (
                urllib.request.urlopen(request, timeout=120) as response,
                partial.open("wb") as stream,
            ):
                shutil.copyfileobj(response, stream)
            partial.replace(raw)
        finally:
            partial.unlink(missing_ok=True)
    checksum = digest(raw)
    if source.get("sha256") and checksum != source["sha256"]:
        raise ValueError(f"download checksum mismatch: {name}")
    return raw, checksum


def _xlsx_rows(path):
    """Stream OOXML rows, including shared strings and Excel numeric dates."""
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    if element.tag == namespace + "si":
                        strings.append("".join(element.itertext()))
                        element.clear()
        for sheet in sorted(
            n
            for n in archive.namelist()
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        ):
            header = None
            with archive.open(sheet) as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    if element.tag != namespace + "row":
                        continue
                    values = {}
                    for cell in element:
                        column = "".join(
                            c for c in cell.attrib.get("r", "") if c.isalpha()
                        )
                        value = cell.findtext(namespace + "v", "")
                        if cell.attrib.get("t") == "s":
                            value = strings[int(value)] if value else ""
                        elif cell.attrib.get("t") == "inlineStr":
                            value = "".join(cell.itertext())
                        values[column] = value
                    if header is None:
                        header = values
                    else:
                        yield {
                            label: values.get(column, "")
                            for column, label in header.items()
                        }
                    element.clear()


def _retail_rows(raw, source_format):
    if source_format == "csv":
        with raw.open(newline="") as stream:
            yield from csv.DictReader(stream)
    elif source_format == "zip_xlsx":
        with ZipFile(raw) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".xlsx"))
            # Spooled storage avoids retaining the compressed workbook in RAM.
            import tempfile

            with tempfile.TemporaryFile() as workbook:
                with archive.open(name) as stream:
                    shutil.copyfileobj(stream, workbook)
                workbook.seek(0)
                yield from _xlsx_rows(workbook)
    else:
        raise ValueError("unsupported retail format")


def _retail(raw, config, calendar):
    sales, returns = defaultdict(float), defaultdict(float)
    ignored = 0
    for row in _retail_rows(raw, config["source"]["format"]):
        date = row.get("InvoiceDate", "")
        try:
            event = datetime(1899, 12, 30) + timedelta(days=float(date))
        except ValueError:
            event = datetime.fromisoformat(date)
        bucket = event.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
        if not calendar[0] <= bucket <= calendar[-1]:
            continue
        quantity = float(row["Quantity"])
        if not math.isfinite(quantity):
            raise ValueError("non-finite retail quantity")
        invoice = row.get("Invoice", row.get("InvoiceNo", ""))
        if invoice.upper().startswith("C") or quantity < 0:
            returns[bucket] += abs(quantity)
        elif quantity > 0:
            sales[bucket] += quantity
        else:
            ignored += 1
    return [sales[t] for t in calendar], {
        "returns": [returns[t] for t in calendar],
        "zero_quantity_rows": ignored,
    }


def _energy(raw, config, calendar):
    readings = defaultdict(dict)
    context = ZipFile(raw) if config["source"]["format"] == "zip_txt" else None
    try:
        stream = (
            io.TextIOWrapper(context.open("household_power_consumption.txt"))
            if context
            else raw.open()
        )
        with stream:
            for row in csv.DictReader(stream, delimiter=";"):
                event = datetime.strptime(
                    row["Date"] + " " + row["Time"], "%d/%m/%Y %H:%M:%S"
                ).replace(tzinfo=UTC)
                bucket = event.replace(minute=0, second=0, microsecond=0)
                if not calendar[0] <= bucket <= calendar[-1]:
                    continue
                if event.second != 0 or event.microsecond != 0:
                    raise ValueError("misaligned meter minute")
                if event in readings[bucket]:
                    raise ValueError("duplicate meter minute")
                text = row[config.get("value_column", "Global_active_power")].strip()
                value = None if text in {"?", ""} else float(text)
                if value is not None and not math.isfinite(value):
                    raise ValueError("non-finite meter reading")
                readings[bucket][event] = value
    finally:
        if context:
            context.close()
    values, quality = [], []
    for bucket in calendar:
        samples = readings[bucket]
        valid = [v for v in samples.values() if v is not None]
        # Aligned, unique timestamps within this hour are its exact minute slots.
        complete = len(samples) == len(valid) == 60
        values.append(sum(valid) / 60 if complete else None)
        quality.append(
            {
                "bucket_start": bucket.isoformat(),
                "expected_samples": 60,
                "observed_samples": len(samples),
                "valid_samples": len(valid),
                "complete": complete,
            }
        )
    return values, {"quality": quality}


def _activity(raw, config, calendar):
    if config["source"]["format"] == "csv":
        with raw.open() as stream:
            rows = list(csv.DictReader(stream))
    else:
        rows = json.loads(raw.read_text())["items"]
    values = {}
    for row in rows:
        event = datetime.strptime(str(row["timestamp"]), "%Y%m%d%H").replace(tzinfo=UTC)
        if event in values:
            raise ValueError("duplicate pageview day")
        count = float(row["views"])
        if not math.isfinite(count) or count < 0:
            raise ValueError("invalid pageview count")
        values[event] = count
    return [values.get(t) for t in calendar], {}


def _write_observations(path, name, config, calendar, values):
    step = frequency_step(config["frequency"])
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for start, value in zip(calendar, values, strict=True):
            # Right-end labels: the complete bucket is assumed known at its end.
            event_time = start if config.get("label_at_start") else start + step
            end = event_time.isoformat()
            writer.writerow(
                dict(
                    series_id=name,
                    event_time=end,
                    available_at=end,
                    revision="assumed-v1",
                    value="" if value is None else value,
                    unit=config["unit"],
                )
            )


def _m4_values(path, series_id):
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("V1") == series_id:
                cells = []
                for key, value in row.items():
                    if key == "V1":
                        continue
                    cells.extend(value if key is None and value else [value])
                values = [(value or "").strip() for value in cells]
                while values and not values[-1]:
                    values.pop()
                if not values or any(not value for value in values):
                    raise ValueError(f"M4 {series_id} has missing values in its series")
                parsed = [float(value) for value in values]
                if any(not math.isfinite(value) for value in parsed):
                    raise ValueError(f"M4 {series_id} contains a non-finite value")
                return parsed
    raise ValueError(f"M4 series not found: {series_id}")


def _m4_daily(raw, config):
    series_id = config["series_id"]
    with raw["info"].open(newline="") as stream:
        info = next(
            (row for row in csv.DictReader(stream) if row.get("M4id") == series_id),
            None,
        )
    if info is None or info.get("Frequency") != "1" or info.get("SP") != "Daily":
        raise ValueError(
            f"M4 series must be declared in metadata as daily: {series_id}"
        )
    expected_category = config.get("expected_category")
    category = info.get("Category", info.get("category"))
    if expected_category and category != expected_category:
        raise ValueError(
            f"M4 category does not match manifest for {series_id}: {category}"
        )
    if int(info["Horizon"]) != config["horizon"]:
        raise ValueError(f"M4 horizon does not match manifest: {series_id}")
    train = _m4_values(raw["train"], series_id)
    test = _m4_values(raw["test"], series_id)
    if len(test) != config["horizon"]:
        raise ValueError(f"M4 test horizon is incomplete: {series_id}")
    start = datetime.strptime(info["StartingDate"], "%d-%m-%y %H:%M").replace(
        tzinfo=UTC
    )
    values = [*train, *test]
    calendar = tuple(start + timedelta(days=index) for index in range(len(values)))
    return (
        calendar,
        values,
        {
            "start": calendar[0].isoformat(),
            "end": calendar[-1].isoformat(),
            "rows": len(values),
            "missing": 0,
            "train_rows": len(train),
            "official_test_rows": len(test),
            "official_horizon": int(info["Horizon"]),
            "category": category,
        },
    )


def _m5_source_files(manifest, config):
    source = config["source"]
    if source.get("format") != "m5_official_csv_bundle":
        raise ValueError("unsupported M5 source format")
    expected_files = source.get("files", {})
    if set(expected_files) != set(M5_SOURCE_FILES):
        raise ValueError("M5 source manifest must pin all six original CSV files")

    directory = Path(manifest.parent / source["directory"])
    checksums_path = Path(manifest.parent / source["checksums_file"])
    registered = json.loads(checksums_path.read_text())
    for key in ("source_repository", "source_folder"):
        if registered.get(key) != source.get(key):
            raise ValueError(f"M5 source provenance mismatch: {key}")
    registered_files = registered.get("files", {})
    if set(registered_files) != set(M5_SOURCE_FILES):
        raise ValueError("M5 checksum register must list all six original CSV files")

    paths, checksums = {}, {}
    for name in M5_SOURCE_FILES:
        expected = expected_files[name]
        recorded = registered_files[name]
        if (
            expected.get("sha256") != recorded.get("sha256")
            or expected.get("bytes") != recorded.get("bytes")
            or expected.get("source") != recorded.get("source")
        ):
            raise ValueError(f"M5 source manifest mismatch: {name}")
        path = directory / name
        if not path.is_file():
            raise ValueError(f"M5 source file is missing: {name}")
        if path.stat().st_size != expected["bytes"]:
            raise ValueError(f"M5 source size mismatch: {name}")
        checksum = digest(path)
        if checksum != expected["sha256"]:
            raise ValueError(f"M5 source checksum mismatch: {name}")
        paths[name] = path
        checksums[name] = checksum
    return paths, checksums


def _m5_retail(raw, config):
    """Aggregate official M5 training units across all item-store rows by day."""
    dates_by_day = {}
    with raw["calendar.csv"].open(newline="") as stream:
        reader = csv.DictReader(stream)
        has_day_ids = "d" in (reader.fieldnames or ())
        for index, row in enumerate(reader, start=1):
            day = row.get("d", "").strip() if has_day_ids else f"d_{index}"
            value = row.get("date", "").strip()
            if not day or day in dates_by_day:
                raise ValueError("M5 calendar has an empty or duplicate day ID")
            try:
                event_date = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError as error:
                raise ValueError("M5 calendar contains an invalid date") from error
            dates_by_day[day] = event_date

    identifiers = ("item_id", "dept_id", "cat_id", "store_id", "state_id")
    totals, dates, seen = None, None, set()
    source_rows = 0
    with raw["sales_train_validation.csv"].open(newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header is None or tuple(header[:5]) != identifiers:
            raise ValueError("M5 training CSV has an unexpected identifier header")
        day_columns = header[5:]
        expected_days = [f"d_{index}" for index in range(1, len(day_columns) + 1)]
        if not day_columns or day_columns != expected_days:
            raise ValueError("M5 training CSV day columns must be contiguous from d_1")
        if any(day not in dates_by_day for day in day_columns):
            raise ValueError("M5 training CSV contains a day absent from its calendar")
        dates = [dates_by_day[day] for day in day_columns]
        if any(
            current - previous != timedelta(days=1)
            for previous, current in pairwise(dates)
        ):
            raise ValueError("M5 training calendar dates must be consecutive")
        totals = [0] * len(day_columns)

        for row in reader:
            if len(row) != len(header):
                raise ValueError("M5 training CSV contains a malformed row")
            if any(not row[index].strip() for index in range(5)):
                raise ValueError("M5 training CSV has an empty series identifier")
            series_key = (row[0], row[3])
            if series_key in seen:
                raise ValueError(
                    "M5 training CSV contains a duplicate item-store series"
                )
            seen.add(series_key)
            source_rows += 1
            for index, cell in enumerate(row[5:]):
                try:
                    value = int(cell)
                except ValueError as error:
                    raise ValueError(
                        "M5 sales values must be integer unit counts"
                    ) from error
                if value < 0:
                    raise ValueError("M5 sales values cannot be negative")
                totals[index] += value

    expected_rows = config.get("expected_source_rows")
    if expected_rows is not None and source_rows != expected_rows:
        raise ValueError(
            f"M5 training series count mismatch: expected {expected_rows}, got {source_rows}"
        )
    return (
        dates,
        totals,
        {
            "rows": len(dates),
            "missing": 0,
            "source_series_rows": source_rows,
            "aggregated_series_count": 1,
            "source_files_used": list(M5_SERIES_FILES),
            "source_files_verified": sorted(M5_SOURCE_FILES),
        },
    )


def prepare_suite(manifest: Path, destination: Path) -> dict[str, Path]:
    manifest, destination = Path(manifest), Path(destination)
    specification = load_manifest(manifest)
    destination.mkdir(parents=True, exist_ok=True)
    metadata = {"manifest_sha256": digest(manifest), "datasets": {}}
    prepared = {}
    recipes = {
        "retail": _retail,
        "energy": _energy,
        "activity": _activity,
        "m4_daily": _m4_daily,
        "m5_retail": _m5_retail,
    }
    for name, config in specification["datasets"].items():
        if config["assumed_available_at"] != "period_end_UTC":
            raise ValueError("unsupported assumed availability recipe")
        if config["recipe"] == "m5_retail":
            raw, checksums = _m5_source_files(manifest, config)
            calendar, values, extra = _m5_retail(raw, config)
            checksum = hashlib.sha256(
                json.dumps(checksums, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            coverage = {
                "start_bucket": calendar[0].isoformat(),
                "end_bucket": calendar[-1].isoformat(),
                "rows": len(values),
                "missing": 0,
                **extra,
            }
        elif config["recipe"] == "m4_daily":
            sources = config["source"].get("files", {})
            if set(sources) != {"info", "train", "test"}:
                raise ValueError("M4 daily sources require info, train, and test files")
            raw, checksums = {}, {}
            for key in ("info", "train", "test"):
                raw[key], checksums[key] = _raw(
                    manifest, config, destination, f"{name}.{key}", sources[key]
                )
            calendar, values, extra = _m4_daily(raw, config)
            checksum = hashlib.sha256(
                json.dumps(checksums, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            coverage = {
                "start_bucket": extra["start"],
                "end_bucket": extra["end"],
                "rows": extra["rows"],
                "missing": extra["missing"],
                "train_rows": extra["train_rows"],
                "official_test_rows": extra["official_test_rows"],
                "category": extra["category"],
            }
        else:
            calendar = bucket_calendar(config)
            raw_source, checksum = _raw(manifest, config, destination, name)
            values, extra = recipes[config["recipe"]](raw_source, config, calendar)
            coverage = {
                "start_bucket": config["start"],
                "end_bucket": config["end"],
                "rows": len(values),
                "missing": sum(v is None for v in values),
            }
        path = destination / f"{name}.csv"
        write_config = dict(config)
        if config["recipe"] == "m4_daily":
            write_config["label_at_start"] = True
        _write_observations(path, config["series_id"], write_config, calendar, values)
        if "returns" in extra:
            _write_observations(
                destination / f"{name}.returns.csv",
                name + ":returns",
                config,
                calendar,
                extra["returns"],
            )
        if "quality" in extra:
            write_json(destination / f"{name}.quality.json", extra["quality"])
        metadata["datasets"][name] = {
            "source": config["source"],
            "download_sha256": checksum,
            "prepared_sha256": digest(path),
            "coverage": coverage,
            "recipe": config,
            "availability_basis": "assumed_not_observed",
        }
        prepared[name] = path
    write_json(destination / "preparation.json", metadata)
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {k: str(v) for k, v in prepare_suite(args.manifest, args.output).items()}
        )
    )


if __name__ == "__main__":
    main()
