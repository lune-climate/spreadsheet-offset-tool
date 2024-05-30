import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from typing import NoReturn

import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from spreadsheet_offset_tool.csv import load_csv, save_csv
from spreadsheet_offset_tool.lune_client import (
    Account,
    ApiResponseError,
    BundlePortolio,
    ErrorCode,
    LuneClient,
    SustainabilityPage,
)


class CustomArgumentParser(argparse.ArgumentParser):
    """A custom argument parser to provide a verbose help screen in case of
    a parsing error."""

    def error(self, message: str) -> NoReturn:
        sys.stderr.write(f"Error: {message}\n\n")
        self.print_help(sys.stderr)
        sys.exit(1)


parser = CustomArgumentParser(
    prog="spreadsheet-offset-tool",
    description="Offset emissions based on spreadsheet contents",
)
parser.add_argument(
    "-i",
    "--input-file",
    help="The CSV spreadsheet file to read data from and write back to",
    type=str,
    required=True,
)
parser.add_argument(
    "-l",
    "--logo-file",
    help="The path to a file with the company logo (.jpg, .jpeg or .png)",
)
parser.add_argument(
    "-b",
    "--beneficiary",
    help="The aggregate name to use for purchasing and retiring of carbon offsets, \
for example: Acme Corporation's customers",
    required=True,
)
parser.add_argument(
    "--allow-live",
    help="Allows running this application against live API keys and live accounts. Disabled by default.",
    action="store_true",
)


@dataclass
class Args:
    """A type-safe structure to hold the application arguments."""

    input_file: str
    logo_file: str
    allow_live: bool
    beneficiary: str
    lune_api_key: str
    lune_api_url: str


def get_args() -> Args:
    """Gathers application arguments from the command line and environment variables."""
    parsed = parser.parse_args()
    lune_api_key = os.environ.get("LUNE_API_KEY")
    if not lune_api_key:
        raise AssertionError(
            "Lune API key has to be provided in the LUNE_API_KEY environment variable"
        )

    return Args(
        input_file=parsed.input_file,
        logo_file=parsed.logo_file,
        allow_live=bool(parsed.allow_live),
        beneficiary=parsed.beneficiary,
        lune_api_key=lune_api_key,
        # This is useful only when running this code against a development instance of
        # the Lune API. End-users won't override this.
        lune_api_url=os.environ.get("LUNE_API_URL", "https://api.lune.co"),
    )


@dataclass
class ClientAccountState:
    account: Account
    page: SustainabilityPage

    def sustainability_page_url(self) -> str:
        extra = "test/" if self.account.type == "test" else ""
        return f"https://sustainability.lune.co/{extra}{self.page.slug}"


def ensure_client_accounts(
    *,
    client: LuneClient,
    names: set[str],
    logo_file: str | None,
    currency: str,
    beneficiary: str,
) -> dict[str, ClientAccountState]:
    """Ensures that properly configured client accounts for given names exist and returns them."""
    client_accounts = client.list_all_client_accounts().expect_success().data
    mapped_accounts = {a.name: a for a in client_accounts}
    if len(mapped_accounts) != len(client_accounts):
        raise AssertionError(
            f"Detected some non-unique client account names in {client_accounts}"
        )

    sustainability_pages: dict[str, SustainabilityPage] = {}

    for index, name in enumerate(names):
        print(f"Processing name {index + 1} out of {len(names)}...")
        # We need to make sure three things are in order...
        # 1. A client account itself
        account = mapped_accounts.get(name)
        if not account:
            print(f"Creating client account for {name}...")
            account = (
                client.create_client_account(
                    name=name,
                    currency=currency,
                    beneficiary=beneficiary,
                )
                .expect_success()
                .data
            )
            mapped_accounts[name] = account
            print("Done.")

        # 2. The logo
        if logo_file:
            # The Lune API doesn't currently return the logo URLs if they're set,
            # so we have to upload the logo just in case.
            print(f"Uploading logo for {name=} {account.id=}...")
            client.update_client_account_logo(
                account_id=account.id, logo_path=logo_file
            ).expect_success().data
            print("Done.")

        # 3. The sustainability page configuration
        response = client.get_sustainability_page(account_id=account.id)
        if isinstance(response, ApiResponseError):
            assert (
                response.status_code == 404
            ), "We only expect 404 here but got {response}"
            # We need to define the slug in a way that's deterministic but also unlikely to
            # cause conflicts with existing sustainability pages (regardless of the customer).
            #
            # It doesn't need to be cryptographically strong so SHA1 is more than good enough.
            slug = hashlib.sha1(f"{beneficiary} {account.id}".encode()).hexdigest()
            print(
                f"Creating a sustainability page for {account.id=} {name=} {slug=}..."
            )
            sustainability_page = (
                client.create_sustainability_page(
                    account_id=account.id, slug=slug, description=f"On behalf of {name}"
                )
                .expect_success()
                .data
            )
            print("Done.")
        else:
            sustainability_page = response.expect_success().data
        sustainability_pages[name] = sustainability_page

    return {
        name: ClientAccountState(
            account=mapped_accounts[name], page=sustainability_pages[name]
        )
        for name in names
    }


def get_bundle_portfolio_by_label(client: LuneClient, label: str) -> BundlePortolio:
    bundle_portfolios = client.list_all_bundle_portfolios().expect_success().data
    portfolio = [p for p in bundle_portfolios if p.label == label]
    if len(portfolio) == 0:
        raise AssertionError(
            f"Failed to find {repr(label)}, portfolios available: {bundle_portfolios}"
        )
    if len(portfolio) > 1:
        raise AssertionError(f"Non-unique portfolios when looking for {repr(label)}")
    return portfolio[0]


def create_lune_client(args: Args) -> LuneClient:
    requests_session = requests.Session()

    # This retry policy is fine for now but if this code is modified to make
    # different API calls, some of which may not be so quite ok to retry, the retry
    # policy may need to be adjusted.
    retries = Retry(
        # Some initial values that look roughly ok. They may need some tuning.
        total=5,
        backoff_factor=0.2,
        # Lune API returns HTTP 429 when the client makes requests too fast.
        # If we get HTTP 429 it's safe to retry.
        status_forcelist=[429],
        allowed_methods={"GET", "POST"},
    )
    for scheme in ["http", "https"]:
        requests_session.mount(f"{scheme}://", HTTPAdapter(max_retries=retries))

    return LuneClient(requests_session, args.lune_api_key, args.lune_api_url)


def main() -> None:
    args = get_args()
    client = create_lune_client(args)

    main_account = client.get_account().expect_success().data

    # The main safety check
    if main_account.type == "live" and args.allow_live is False:
        raise AssertionError(
            """Live Lune API key detected but live mode not permitted.
this is a safety mechanism. Use --allow-live to enable live mode.
This will allow you to interact with live accounts and place real, live orders.
""",
        )

    # Dump some debugging information
    print(f"The main account: {main_account}")

    rows = load_csv(input_file=args.input_file)
    accounts = ensure_client_accounts(
        client=client,
        names={r.recipients_name for r in rows},
        logo_file=args.logo_file,
        beneficiary=args.beneficiary,
        currency=main_account.currency,
    )
    portfolio = get_bundle_portfolio_by_label(
        client, "Oxford Offsetting Principles Portfolio"
    )
    print(f"Found portfolio: {portfolio}")

    for index, row in enumerate(rows):
        print(f"Processing row {index + 1} out of {len(rows)}...")
        account_state = accounts[row.recipients_name]
        row.sustainability_page_url = account_state.sustainability_page_url()

        if row.order_id:
            # Nothing to do here, we already placed this order.
            continue

        # The idempotency key mechanism allows us to prevent placing redundant orders and
        # makes it safe to retry order placement.
        #
        # It needs to be a deterministic value so a hash function works here.
        #
        # It doesn't need to be cryptographically strong so SHA1 is more than good enough.
        idempotency_key = hashlib.sha1(
            f"{row.timestamp} {row.recipients_name} 2kg".encode()
        ).hexdigest()

        print(f"Placing an order for {account_state.account.id=} {idempotency_key=}...")
        order_response = client.create_order_by_mass(
            account_id=account_state.account.id,
            idempotency_key=idempotency_key,
            mass_grams=int((row.quantity_kg or 2.0) * 1000.0),
            bundle_selection=portfolio.bundle_selection,
        )
        if (
            isinstance(order_response, ApiResponseError)
            and order_response.error_code
            == ErrorCode.order_idempotency_already_exists.value
        ):
            print(f"We already have an order for {idempotency_key=}, fetching...")
            order = (
                client.get_order_by_idempotency_key(
                    account_id=account_state.account.id, idempotency_key=idempotency_key
                )
                .expect_success()
                .data
            )
        else:
            order = order_response.expect_success().data
        print(f"Done, {order.id=}.")

        row.order_id = order.id

        # We save on every iteration so that we can keep track of the progress in
        # the output file. Then if the application is interrupted we can run it again
        # and we'll pick up where we left off.
        #
        # The tool is implemented so that one should be able to run it again and it should
        # do the right thing even without past progress available but it'd have to do
        # some redundant work. Let's try to avoid that.
        save_csv(args.input_file, rows)

    print()
    print(f"Success! Find your results in {args.input_file}.")
