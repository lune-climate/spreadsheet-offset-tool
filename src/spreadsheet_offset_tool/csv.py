import csv
from dataclasses import dataclass
from typing import TextIO


@dataclass
class CsvRow:
    # We extract these values when parsing CSV so that we can keep using them later
    # in a type-safe way.
    timestamp: str
    recipients_name: str
    recipients_email: str
    quantity_kg: float | None

    # These will be empty in input rows but eventually filled in output rows.
    order_id: str
    sustainability_page_url: str

    # All contents of a CSV row (including the timestamp and recipient's name).
    values: dict[str, str]

    def __post_init__(self) -> None:
        if self.timestamp.strip() != self.timestamp:
            raise ValueError(
                f"Leading or trailing space in timestamp {repr(self.timestamp)} detected"
            )
        if self.recipients_name.strip() != self.recipients_name:
            raise ValueError(
                f"Leading or trailing space in timestamp {repr(self.recipients_name)} detected"
            )

    def account_name(self) -> str:
        """Something that can be unique across all customers. A name won't necessarily
        be unique on its own.
        """
        return f"{self.recipients_name} ({self.recipients_email})"


def load_csv(*, input_file: str) -> list[CsvRow]:
    """Loads the CSV rows from provided file.

    input_file is read unconditionally and has to exist.
    """
    with open(input_file) as f:
        return _parse_csv(f)


def save_csv(output_file: str, rows: list[CsvRow]) -> None:
    to_save = [
        r.values
        | {
            "lune_order_id": r.order_id,
            "lune_sustainability_page_url": r.sustainability_page_url,
        }
        for r in rows
    ]
    field_names = list(to_save[0].keys())
    with open(output_file, "w") as f:
        # Unix dialect for LF newline characters instead of CRLF
        writer = csv.DictWriter(f, field_names, dialect="unix")
        writer.writeheader()
        writer.writerows(to_save)


def _parse_csv(
    f: TextIO,
) -> list[CsvRow]:
    reader = csv.DictReader(f)
    results: list[CsvRow] = []
    for r in reader:
        try:
            timestamp = r["Timestamp"]
            recipients_name = r["Certificate recipient's name"]
            recipients_email = r["Email address"]
        except KeyError as e:
            raise AssertionError(f"Could not find an expected CSV field: {e}")
        order_id = r.get("lune_order_id", "")
        sustainability_page_url = r.get("lune_sustainability_page_url", "")
        quantity_kg_text = r.get("Offset quantity kg")
        if order_id != "" and sustainability_page_url == "":
            raise AssertionError(f"{order_id=} present but no sustainability page URL")

        results.append(
            CsvRow(
                timestamp=timestamp,
                recipients_name=recipients_name,
                recipients_email=recipients_email,
                quantity_kg=float(quantity_kg_text) if quantity_kg_text else None,
                order_id=order_id,
                sustainability_page_url=sustainability_page_url,
                values=r,
            )
        )
    return results
