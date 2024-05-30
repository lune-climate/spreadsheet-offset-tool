# spreadsheet-offset-tool

## What is this?

This is a Python tool that consumes a CSV spreadsheet and integrates with the
[Lune API](https://docs.lune.co/) to perform actions based on the fi.e contents.

The tool goes through the provided CSV file and for every row:

* It ensures that an appropriate [client account](https://docs.lune.co/key-concepts/client-accounts)
  exists and it has its [sustainability page](https://docs.lune.co/guides/share-your-impact)
  configured with your logo on it
* Places an order on a portfolio following Oxford Offsetting Principles
* Presents the order id and the sustainability page URL in the same CSV file as new columns

The offsets will be retired under the name of your choice (common for all orders)
but the sustainability pages will display the names of your customers (one name
per sustainability page).

You can then share the sustainability page URLs with your customers.

## The expected data format

Two columns are required to be present in the input CSV file (the names are case-sensitive,
no leading or trailing whitespace allowed):

* `Timestamp` – used to disambiguate records
* `Certificate recipient's name` – the name of your customer
* `Offset quantity kg` – the amount of CO2 to offset, if the column is missing or empty for
  a given row we default to 2 kg

If the same `Certificate recipient's name` name appears multiple times in the input CSV
file it is assumed to refer to the same person.

Other fields are permitted as preserved in the output CSV file.

An example input file has been provided for your convenience: `input_example.csv`.

## Prerequisites

### Dependencies

Python 3.12+ and Poetry are required.

To install the project's dependencies:

```
# Only runtime dependencies
poetry install --only main

# Or, including development dependencies
poetry install
```

### API keys

You need a [Lune API key](https://docs.lune.co/key-concepts/authentication#creating-an-api-key)
to run this code.

[Live and test API keys](https://docs.lune.co/key-concepts/live-test-accounts) are supported.

Once you have an API key you need to export it in an environment variable named `LUNE_API_KEY`.

## Usage

### Common usage

Assuming

* Your name is `ACME`
* You have the input data in `input.csv`
* Your company's logo is placed in `logo.png`

this is how you'll want to run it:

```
# Only test API keys allowed here
poetry run spreadsheet-offset-tool \
    -i input.csv \
    -b "ACME's customers" \
    -l logo.png

# Live API key spermitted
poetry run spreadsheet-offset-tool \
    -i input.csv \
    -b "ACME's customers" \
    -l logo.png \
    --allow-live
```

The tool will update the input CSV file as it progresses and if it's interrupted it can be
safely restarted with the same parameters.

It is advised to test things with a test API key to make sure everything works as expected.

### Full usage details

```
% poetry run spreadsheet-offset-tool --help
usage: spreadsheet-offset-tool [-h] -i INPUT_FILE [-l LOGO_FILE] -b BENEFICIARY [--allow-live]

Offset emissions based on spreadsheet contents

options:
  -h, --help            show this help message and exit
  -i INPUT_FILE, --input-file INPUT_FILE
                        The input CSV spreadsheet file
  -l LOGO_FILE, --logo-file LOGO_FILE
                        The path to a file with the company logo (.jpg, .jpeg or .png)
  -b BENEFICIARY, --beneficiary BENEFICIARY
                        The aggregate name to use for purchasing and retiring of carbon offsets, for example: Acme Corporation's customers
  --allow-live          Allows running this application against live API keys and live accounts. Disabled by default.
```
