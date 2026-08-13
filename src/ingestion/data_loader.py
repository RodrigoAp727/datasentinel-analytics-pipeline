"""Data loading utilities for local files and REST APIs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import sleep
from typing import Any

import pandas as pd
import requests
from loguru import logger


class DataLoaderError(Exception):
    """Base exception for data loading errors."""


class CSVLoadError(DataLoaderError):
    """Raised when CSV loading fails."""


class APILoadError(DataLoaderError):
    """Raised when API loading fails."""


class APITimeoutError(APILoadError):
    """Raised when API request times out after retries."""


class InvalidJSONError(APILoadError):
    """Raised when API response has invalid JSON content."""


@dataclass(slots=True)
class CSVSource:
    """Configuration for loading a CSV source.

    Attributes:
        name: Identifier used as key in aggregated results.
        path: Path to the CSV file.
        read_csv_kwargs: Optional keyword arguments passed to pandas.read_csv.
    """

    name: str
    path: Path | str
    read_csv_kwargs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class APISource:
    """Configuration for loading a REST API source.

    Attributes:
        name: Identifier used as key in aggregated results.
        url: Endpoint URL.
        params: Optional query string parameters.
        headers: Optional HTTP headers.
        timeout: Timeout in seconds for each request attempt.
    """

    name: str
    url: str
    params: Mapping[str, Any] | None = None
    headers: Mapping[str, str] | None = None
    timeout: float = 10.0


class DataLoader:
    """Loads data from local CSV files and REST APIs.

    This class provides single-source loaders and a multi-source loader that
    returns all successful loads as pandas DataFrames in a dictionary.

    Args:
        max_retries: Number of request attempts for network failures.
        backoff_base_seconds: Base duration used for exponential backoff.
        session: Optional requests session for dependency injection in tests.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        session: requests.Session | None = None,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        if backoff_base_seconds <= 0:
            raise ValueError("backoff_base_seconds must be > 0")

        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.session = session or requests.Session()

    def load_csv(self, path: Path | str, **read_csv_kwargs: Any) -> pd.DataFrame:
        """Load data from a local CSV/Excel file.

        Args:
            path: CSV/Excel file path.
            **read_csv_kwargs: Extra keyword arguments passed to pandas.read_csv
                for .csv files or pandas.read_excel for .xlsx/.xls files.

        Returns:
            DataFrame loaded from the file.

        Raises:
            CSVLoadError: If file is not found, unsupported, malformed, or unreadable.
        """
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        logger.info("Loading tabular file from path={}.", file_path)

        if suffix not in {".csv", ".xlsx", ".xls"}:
            raise CSVLoadError(
                f"Unsupported file format: {file_path}. Use .csv, .xlsx or .xls"
            )

        try:
            if suffix == ".csv":
                dataframe = pd.read_csv(file_path, **read_csv_kwargs)
            else:
                dataframe = pd.read_excel(file_path, **read_csv_kwargs)
        except FileNotFoundError as exc:
            logger.exception("Tabular file not found at path={}", file_path)
            raise CSVLoadError(f"Tabular file not found: {file_path}") from exc
        except pd.errors.EmptyDataError as exc:
            logger.exception("Tabular file is empty at path={}", file_path)
            raise CSVLoadError(f"Tabular file is empty: {file_path}") from exc
        except pd.errors.ParserError as exc:
            logger.exception("Tabular parsing failed at path={}", file_path)
            raise CSVLoadError(f"Tabular parsing failed: {file_path}") from exc
        except ValueError as exc:
            logger.exception("Tabular parsing failed at path={}", file_path)
            raise CSVLoadError(f"Tabular parsing failed: {file_path}") from exc
        except OSError as exc:
            logger.exception("OS error while reading tabular file at path={}", file_path)
            raise CSVLoadError(f"Unable to read tabular file: {file_path}") from exc

        logger.info(
            "Tabular file loaded successfully from path={} with rows={} and cols={}",
            file_path,
            dataframe.shape[0],
            dataframe.shape[1],
        )
        return dataframe

    def load_api(
        self,
        url: str = "https://jsonplaceholder.typicode.com/posts",
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> pd.DataFrame:
        """Load data from a REST API endpoint.

        Args:
            url: REST endpoint URL.
            params: Query parameters.
            headers: HTTP headers.
            timeout: Timeout in seconds for each attempt.

        Returns:
            DataFrame generated from JSON response.

        Raises:
            APITimeoutError: If request times out on all retries.
            InvalidJSONError: If response JSON is invalid.
            APILoadError: For other network/HTTP related failures.
        """
        logger.info("Loading API data from url={}.", url)
        response = self._request_with_retry(
            url=url,
            params=params,
            headers=headers,
            timeout=timeout,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            logger.exception("Invalid JSON response from url={}", url)
            raise InvalidJSONError(f"Invalid JSON response from API: {url}") from exc

        dataframe = self._json_to_dataframe(payload)
        logger.info(
            "API loaded successfully from url={} with rows={} and cols={}",
            url,
            dataframe.shape[0],
            dataframe.shape[1],
        )
        return dataframe

    def load_sources(
        self,
        *,
        csv_sources: Sequence[CSVSource] | None = None,
        api_sources: Sequence[APISource] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Load multiple sources and return them as a dictionary.

        Args:
            csv_sources: Sequence of CSV source configurations.
            api_sources: Sequence of API source configurations.

        Returns:
            Dictionary mapping source names to loaded DataFrames.

        Raises:
            DataLoaderError: If any source fails to load.
        """
        results: dict[str, pd.DataFrame] = {}
        csv_sources = csv_sources or []
        api_sources = api_sources or []

        logger.info(
            "Starting multi-source loading with csv_count={} and api_count={}",
            len(csv_sources),
            len(api_sources),
        )

        for source in csv_sources:
            results[source.name] = self.load_csv(
                source.path,
                **dict(source.read_csv_kwargs),
            )

        for source in api_sources:
            results[source.name] = self.load_api(
                url=source.url,
                params=source.params,
                headers=source.headers,
                timeout=source.timeout,
            )

        logger.info("Multi-source loading completed with total_sources={}", len(results))
        return results

    def _request_with_retry(
        self,
        *,
        url: str,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> requests.Response:
        """Execute HTTP GET with retries and exponential backoff."""
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response
            except requests.Timeout as exc:
                last_error = exc
                logger.warning(
                    "Timeout during API call to url={} on attempt={}/{}",
                    url,
                    attempt,
                    self.max_retries,
                )
                if attempt == self.max_retries:
                    logger.exception("API timeout after retries for url={}", url)
                    raise APITimeoutError(
                        f"API timeout after {self.max_retries} attempts: {url}"
                    ) from exc
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Network/HTTP failure for url={} on attempt={}/{}: {}",
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt == self.max_retries:
                    logger.exception("API load failed after retries for url={}", url)
                    raise APILoadError(
                        f"API request failed after {self.max_retries} attempts: {url}"
                    ) from exc

            sleep_seconds = self.backoff_base_seconds * (2 ** (attempt - 1))
            sleep(sleep_seconds)

        raise APILoadError(f"API request failed: {url}") from last_error

    @staticmethod
    def _json_to_dataframe(payload: Any) -> pd.DataFrame:
        """Convert API JSON payload into a pandas DataFrame.

        Args:
            payload: JSON-decoded Python object.

        Returns:
            DataFrame built from payload.
        """
        if isinstance(payload, list):
            return pd.json_normalize(payload)

        if isinstance(payload, dict):
            return pd.json_normalize(payload)

        return pd.DataFrame({"value": [payload]})
