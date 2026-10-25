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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

from forecast_anything.providers.base import frequency_step

USER_AGENT = "ForecastAnythingBenchmark/0.1 (research; https://github.com/francescogabrieli/forecast_anything)"
FIELDS = ("series_id", "event_time", "available_at", "revision", "value", "unit")


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
    return parsed.astimezone(timezone.utc)


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


def _raw(manifest, config, destination, name):
    source = config["source"]
    source_key = hashlib.sha256(source["url"].encode()).hexdigest()[:16]
    raw = destination / "raw" / f"{name}.{source_key}.download"
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
        bucket = event.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
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
                ).replace(tzinfo=timezone.utc)
                bucket = event.replace(minute=0, second=0, microsecond=0)
                if not calendar[0] <= bucket <= calendar[-1]:
                    continue
                if event in readings[bucket]:
                    raise ValueError("duplicate meter minute")
                text = row["Global_active_power"].strip()
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
        event = datetime.strptime(str(row["timestamp"]), "%Y%m%d%H").replace(
            tzinfo=timezone.utc
        )
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
            end = (start + step).isoformat()
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


def prepare_suite(manifest: Path, destination: Path) -> dict[str, Path]:
    manifest, destination = Path(manifest), Path(destination)
    specification = load_manifest(manifest)
    destination.mkdir(parents=True, exist_ok=True)
    metadata = {"manifest_sha256": digest(manifest), "datasets": {}}
    prepared = {}
    recipes = {"retail": _retail, "energy": _energy, "activity": _activity}
    for name, config in specification["datasets"].items():
        if config["assumed_available_at"] != "period_end_UTC":
            raise ValueError("unsupported assumed availability recipe")
        calendar = bucket_calendar(config)
        raw, checksum = _raw(manifest, config, destination, name)
        values, extra = recipes[config["recipe"]](raw, config, calendar)
        path = destination / f"{name}.csv"
        _write_observations(path, config["series_id"], config, calendar, values)
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
            "coverage": {
                "start_bucket": config["start"],
                "end_bucket": config["end"],
                "rows": len(values),
                "missing": sum(v is None for v in values),
            },
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
