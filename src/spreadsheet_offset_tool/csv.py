import csv
import os
from dataclasses import dataclass
from typing import Literal, TextIO


@dataclass
class CsvRow:
    # We extract these two values when parsing CSV so that we can keep using them later
    # in a type-safe way.
    timestamp: str
    recipients_name: str

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


def load_csvs(*, input_file: str, output_file: str) -> list[CsvRow]:
    """Loads the CSV rows from provided files.

    input_file is read unconditionally and has to exist.

    If output_file exists we do the following:

    * Load the rows from there
    * Verify that the rows are consistent with the rows in input_file
    * Actually use the output_file values when returning from this function

    As the data from output_file takes precedence the client code can store partial results
    in output_file as we can restart/retry at any point.
    """
    with open(input_file) as f:
        input_rows = _parse_csv(f, mode="input")
        to_return = input_rows

    if os.path.isfile(output_file):
        with open(output_file) as f:
            output_rows = _parse_csv(f, mode="output")

        assert (
            len(input_rows) == len(output_rows)
        ), f"Inconsistency: {input_file} and {output_file} have different number of rows"
        for index, (i, o) in enumerate(zip(input_rows, output_rows)):
            cleaned_o = {
                k: v
                for (k, v) in o.values.items()
                if k not in ["lune_order_id", "lune_sustainability_page_url"]
            }
            if i.values != cleaned_o:
                raise AssertionError(
                    f"Row {index} is inconsistent between {input_file} and {output_file}"
                )
        to_return = output_rows
    return to_return


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
    f: TextIO, *, mode: Literal["input"] | Literal["output"]
) -> list[CsvRow]:
    reader = csv.DictReader(f)
    results: list[CsvRow] = []
    for r in reader:
        order_id = ""
        sustainability_page_url = ""

        try:
            timestamp = r["Timestamp"]
            recipients_name = r["Certificate recipient's name"]

            if mode == "output":
                order_id = r["lune_order_id"]
                sustainability_page_url = r["lune_sustainability_page_url"]
        except KeyError as e:
            raise AssertionError(f"Could not find an expected CSV field: {e}")

        if order_id != "" and sustainability_page_url == "":
            raise AssertionError(f"{order_id=} present but no sustainability page URL")

        if mode == "input":
            assert "lune_order_id" not in r, r
            assert "lune_sustainability_page_url" not in r, r

        results.append(
            CsvRow(
                timestamp=timestamp,
                recipients_name=recipients_name,
                order_id=order_id,
                sustainability_page_url=sustainability_page_url,
                values=r,
            )
        )
    return results
