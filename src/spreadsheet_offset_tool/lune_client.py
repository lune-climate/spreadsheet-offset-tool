from dataclasses import dataclass
from enum import Enum
from typing import Any, BinaryIO, Literal, NoReturn, Type, TypeGuard

import requests
from pydantic import BaseModel, TypeAdapter

#
# Error codes as an enum for convenience.
#


class ErrorCode(Enum):
    """Lune API error codes as of 2024-05-23."""

    account_suspended = "account_suspended"
    bundle_selection_ratios_invalid = "bundle_selection_ratios_invalid"
    bundle_selection_bundle_invalid = "bundle_selection_bundle_invalid"
    order_idempotency_already_exists = "order_idempotency_already_exists"
    order_quantity_invalid = "order_quantity_invalid"
    order_value_invalid = "order_value_invalid"
    bundle_id_invalid = "bundle_id_invalid"
    id_invalid = "id_invalid"
    test_account_name_update_disallowed = "test_account_name_update_disallowed"
    validation_error = "validation_error"
    bundle_selection_ratios_invalid_format = "bundle_selection_ratios_invalid_format"
    address_not_found = "address_not_found"
    port_not_found = "port_not_found"
    locode_not_found = "locode_not_found"
    airport_invalid = "airport_invalid"
    webhook_limit_reached = "webhook_limit_reached"
    time_range_invalid = "time_range_invalid"
    exchange_rate_not_found = "exchange_rate_not_found"
    live_account_required = "live_account_required"
    unauthorised = "unauthorised"
    estimate_not_found = "estimate_not_found"
    estimate_order_already_placed = "estimate_order_already_placed"
    sustainability_page_slug_not_unique = "sustainability_page_slug_not_unique"
    sustainability_page_exists = "sustainability_page_exists"
    pagination_limit_invalid = "pagination_limit_invalid"
    unsupported_image_format = "unsupported_image_format"
    source_location_code_invalid = "source_location_code_invalid"
    destination_location_code_invalid = "destination_location_code_invalid"
    emission_factor_id_invalid = "emission_factor_id_invalid"
    emission_factor_unit_mismatch = "emission_factor_unit_mismatch"
    emission_factor_gated = "emission_factor_gated"
    account_scope_incorrect = "account_scope_incorrect"
    service_unavailable = "service_unavailable"
    handle_not_unique = "handle_not_unique"
    estimate_idempotency_already_exists = "estimate_idempotency_already_exists"


#
# The success/error types returnes by LuneClient.
#
# expect_success is a convenience method for when you want to assert you have
# a success response and want to abort the execution if it's not the case.
#


@dataclass
class ApiConnectionError:
    """We failed to get a response from the API."""

    details: ConnectionError | TimeoutError

    def expect_success(self) -> NoReturn:
        raise AssertionError(f"Expected success but got {self}")


@dataclass
class ApiResponseError:
    """We got a response but it indicates an error."""

    status_code: int
    error_code: str | None = None
    message: str | None = None
    request_id: str | None = None

    def expect_success(self) -> NoReturn:
        raise AssertionError(f"Expected success but got {self}")


@dataclass
class ApiSuccess[T]:
    """We got a correct response from the API."""

    data: T
    request_id: str | None

    def expect_success(self) -> "ApiSuccess[T]":
        return self


# Just an alias for convenience.
type ApiResponse[T] = ApiConnectionError | ApiResponseError | ApiSuccess[T]


def is_error[T](
    response: ApiResponse[T],
) -> TypeGuard[ApiConnectionError | ApiResponseError]:
    return isinstance(response, (ApiConnectionError, ApiResponseError))


#
# Lune API model definitions.
#
# There are only a few models below and they only define the subset of the available
# properties – we don't need more than that. We specifically discard any properties
# we don't define here (the extra="ignore" flags in model definitions).
#
# The models are defined by hand, no OpenAPI -> Python code generator available today
# can handle our API specification well.


class Account(BaseModel, extra="ignore"):
    id: str
    name: str
    type: Literal["live"] | Literal["test"]
    scope: Literal["account"] | Literal["client_account"]
    currency: str
    logo: str | None


class ResultPage[T](BaseModel, extra="ignore"):
    data: list[T]
    has_more: bool


class UpdateLogoResult(BaseModel, extra="ignore"):
    url: str


class SustainabilityPage(BaseModel, extra="ignore"):
    slug: str


class Order(BaseModel, extra="ignore"):
    id: str


class BundleSelectionItem(BaseModel, extra="ignore"):
    bundle_id: str
    percentage: int | str


class BundlePortolio(BaseModel, extra="ignore"):
    identifier: str
    label: str
    bundle_selection: list[BundleSelectionItem]


#
# The actual client.
#


@dataclass
class LuneClient:
    """
    This Lune API client is writted by hand, there are no good tools at the moment
    to generate one from an OpenAPI specification.

    The client is not entirely use case-agnostic – it's implemented with the needs of
    this specific tool in mind in some ways. It should be easy to make it more general
    purpose if needed.

    Error handling
    ==============

    The following errors are returned as values from the client methods:

    * Any kind of network/connection problem
    * Timeouts
    * API returning HTTP 4xx/5xx responses

    This is in the interest to make error handling more convenient and predictable.

    On the other hand if something truly unexpected happens (like the API returning
    invalid data) that will just result in an exception, there's nothing we can do
    about it and there's either something wrong with the API or this code needs fixing.
    """

    session: requests.Session
    api_key: str
    api_url: str

    def get_account(self) -> ApiResponse[Account]:
        """Fetches the default account associated with the API key used."""
        return self._request(
            method="get",
            path="accounts/me",
            model_class=Account,
        )

    def list_all_client_accounts(self) -> ApiResponse[list[Account]]:
        """Fetches all client accounts available via the API key."""
        accounts: list[Account] = []
        after = None
        request_id = None
        while True:
            params = {
                "limit": "100",
            }
            if after is not None:
                params["after"] = after
            response = self._request(
                method="get",
                path="accounts/client",
                model_class=ResultPage[Account],
                params=params,
            )
            if is_error(response):
                return response
            # An assertion to make Mypy happy, it doesn't perform type narrowing here.
            assert isinstance(response, ApiSuccess)
            accounts += response.data.data
            request_id = response.request_id
            if response.data.has_more is False:
                break
            after = response.data.data[-1].id

        # We'll just use the last seen request_id here.
        return ApiSuccess(data=accounts, request_id=request_id)

    def create_client_account(
        self, *, name: str, currency: str, beneficiary: str
    ) -> ApiResponse[Account]:
        return self._request(
            method="post",
            path="accounts/client",
            json={
                "name": name,
                "currency": currency,
                "beneficiary": beneficiary,
            },
            model_class=Account,
        )

    def update_client_account_logo(
        self, *, account_id: str, logo_path: str
    ) -> ApiResponse[UpdateLogoResult]:
        with open(logo_path, "rb") as f:
            return self._request(
                method="post",
                path=f"accounts/client/{account_id}/logo",
                files={
                    "logo": f,
                },
                model_class=UpdateLogoResult,
            )

    def get_sustainability_page(
        self, *, account_id: str
    ) -> ApiResponse[SustainabilityPage]:
        return self._request(
            method="get",
            path="sustainability-pages/current-account",
            headers={"Lune-Account": account_id},
            model_class=SustainabilityPage,
        )

    def create_sustainability_page(
        self,
        *,
        account_id: str,
        slug: str,
        description: str,
    ) -> ApiResponse[SustainabilityPage]:
        json_data = {
            "status": "enabled",
            "slug": slug,
            "title": "by_volume",
            "description": "by_custom_description",
            "custom_description": description,
            "sections": ["bundles_breakdown", "certificates"],
        }
        return self._request(
            method="post",
            path="sustainability-pages",
            headers={"Lune-Account": account_id},
            json=json_data,
            model_class=SustainabilityPage,
        )

    def list_all_bundle_portfolios(
        self,
    ) -> ApiResponse[list[BundlePortolio]]:
        return self._request(
            method="get",
            path="bundle-portfolios",
            model_class=TypeAdapter(list[BundlePortolio]),
        )

    def create_order_by_mass(
        self,
        *,
        account_id: str,
        idempotency_key: str,
        mass_grams: int,
        bundle_selection: list[BundleSelectionItem],
    ) -> ApiResponse[Order]:
        json_data = {
            "mass": {
                "amount": str(mass_grams),
                "unit": "g",
            },
            "idempotency_key": idempotency_key,
            "bundle_selection": [b.model_dump() for b in bundle_selection],
        }
        return self._request(
            method="post",
            path="orders/by-mass",
            headers={"Lune-Account": account_id},
            json=json_data,
            model_class=Order,
        )

    def get_order_by_idempotency_key(
        self,
        *,
        account_id: str,
        idempotency_key: str,
    ) -> ApiResponse[Order]:
        return self._request(
            method="get",
            path=f"orders/by-idempotency-key/{idempotency_key}",
            headers={"Lune-Account": account_id},
            model_class=Order,
        )

    def _request[T](
        self,
        *,
        method: Literal["get"] | Literal["post"],
        path: str,
        model_class: Type[T] | TypeAdapter[T],
        data: Any = None,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        files: dict[str, BinaryIO] | None = None,
    ) -> ApiResponse[T]:
        assert not path.startswith("/"), path
        url = f"{self.api_url}/v1/{path}"
        headers = (headers or {}) | {
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                data=data,
                json=json,
                params=params,
                files=files,
            )
        except (ConnectionError, TimeoutError) as e:
            return ApiConnectionError(e)

        request_id = response.headers.get("cf-ray")
        if response.status_code >= 400:
            # For our purposes we assume that if we have a response it'll be valid JSON
            error = (
                response.json()["error"]
                if response.headers.get("Content-Type", "").startswith(
                    "application/json"
                )
                else None
            )
            return ApiResponseError(
                status_code=response.status_code,
                error_code=error["error_code"] if error else None,
                message=error["message"] if error else None,
                request_id=request_id,
            )
        if response.status_code >= 300:
            raise AssertionError(
                f"Unexpected status code {response.status_code}, {request_id=}"
            )

        # Here we perform JSON decoding and validate the data received.
        #
        # If anything goes wrong with this it'll raise an exception.
        #
        # We don't attempt to handle that, it goes wrong it means there's a programming
        # error somewhere (in the API or in this code) and there's nothing
        # we can do without fixing that.
        model = (
            model_class.validate_json(response.text)
            if isinstance(model_class, TypeAdapter)
            else model_class(**response.json())
        )

        return ApiSuccess(
            data=model,
            request_id=request_id,
        )
