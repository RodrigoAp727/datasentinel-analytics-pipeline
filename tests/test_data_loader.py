from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from ingestion.data_loader import (
    APISource,
    APITimeoutError,
    CSVLoadError,
    CSVSource,
    DataLoader,
)


def test_load_csv_success(tmp_path: Path) -> None:
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("id,name\n1,Ana\n2,Caio\n", encoding="utf-8")

    loader = DataLoader()
    dataframe = loader.load_csv(csv_file)

    assert list(dataframe.columns) == ["id", "name"]
    assert dataframe.shape == (2, 2)
    assert dataframe.loc[0, "name"] == "Ana"


def test_load_csv_file_not_found() -> None:
    loader = DataLoader()

    with pytest.raises(CSVLoadError, match="Tabular file not found"):
        loader.load_csv("missing_file.csv")


def test_load_excel_success(tmp_path: Path) -> None:
    excel_file = tmp_path / "sample.xlsx"
    input_df = pd.DataFrame({"id": [1, 2], "name": ["Ana", "Caio"]})
    input_df.to_excel(excel_file, index=False)

    loader = DataLoader()
    dataframe = loader.load_csv(excel_file)

    assert list(dataframe.columns) == ["id", "name"]
    assert dataframe.shape == (2, 2)
    assert dataframe.loc[1, "name"] == "Caio"


@patch("ingestion.data_loader.sleep", return_value=None)
def test_load_api_timeout_with_retry(mock_sleep: MagicMock) -> None:
    mocked_session = MagicMock()
    mocked_session.get.side_effect = requests.Timeout("timed out")

    loader = DataLoader(max_retries=3, backoff_base_seconds=0.01, session=mocked_session)

    with pytest.raises(APITimeoutError, match="API timeout"):
        loader.load_api(url="https://jsonplaceholder.typicode.com/posts", timeout=0.01)

    assert mocked_session.get.call_count == 3
    assert mock_sleep.call_count == 2


@patch("ingestion.data_loader.sleep", return_value=None)
def test_load_sources_multiple_success(mock_sleep: MagicMock, tmp_path: Path) -> None:
    csv_file = tmp_path / "batch.csv"
    csv_file.write_text("id,value\n1,100\n2,200\n", encoding="utf-8")

    mocked_response = MagicMock()
    mocked_response.raise_for_status.return_value = None
    mocked_response.json.return_value = [{"id": 10, "title": "post"}]

    mocked_session = MagicMock()
    mocked_session.get.return_value = mocked_response

    loader = DataLoader(session=mocked_session)
    result = loader.load_sources(
        csv_sources=[CSVSource(name="local_csv", path=csv_file)],
        api_sources=[
            APISource(
                name="posts_api",
                url="https://jsonplaceholder.typicode.com/posts",
                timeout=1.0,
            )
        ],
    )

    assert set(result.keys()) == {"local_csv", "posts_api"}
    assert isinstance(result["local_csv"], pd.DataFrame)
    assert isinstance(result["posts_api"], pd.DataFrame)
    assert result["local_csv"].shape == (2, 2)
    assert result["posts_api"].shape == (1, 2)
    assert mock_sleep.call_count == 0
