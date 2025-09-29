"""Apex Omni endpoint and credential configuration helper.

This module centralizes the websocket and REST base URLs together with
account credentials sourced from ``apex-taker/omni_config.json`` so that
other components can consume a single, structured configuration object.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# Base endpoints grouped by Omni network identifier.
NETWORK_ENDPOINTS: Dict[int, Dict[str, str]] = {
    9: {
        "name": "omni_mainnet",
        "http_base": "https://omni.apex.exchange",
        "public_wss": "wss://quote.omni.apex.exchange/realtime_public?v=2",
        "private_wss": "wss://quote.omni.apex.exchange/realtime_private?v=2",
    },
    3: {
        "name": "omni_testnet_bnb",
        "http_base": "https://qa.omni.apex.exchange",
        "public_wss": "wss://qa-quote.omni.apex.exchange/realtime_public?v=2",
        "private_wss": "wss://qa-quote.omni.apex.exchange/realtime_private?v=2",
    },
    11: {
        "name": "omni_testnet_base",
        "http_base": "https://qa.omni.apex.exchange",
        "public_wss": "wss://qa-quote.omni.apex.exchange/realtime_public?v=2",
        "private_wss": "wss://qa-quote.omni.apex.exchange/realtime_private?v=2",
    },
}

# Key REST API paths used by the taker and market-maker workflows.
REST_API_PATHS: Dict[str, str] = {
    "create_order": "/api/v3/order",
    "open_orders": "/api/v3/open-orders",
    "get_order": "/api/v3/order",
    "get_order_by_client_id": "/api/v3/order-by-client-order-id",
    "history_orders": "/api/v3/history-orders",
    "cancel_order": "/api/v3/order",
    "cancel_all": "/api/v3/open-orders",
    "fills": "/api/v3/fills",
    "server_time": "/api/v1/time",
}

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "apex-taker" / "omni_config.json"


@dataclass
class ApexAccount:
    """Represents a single Omni account credential set."""

    label: str
    ethereum_address: str
    account_id: str
    sub_account_id: str
    api_key: Dict[str, str]
    zk: Dict[str, str]


@dataclass
class ApexConfig:
    """Structured Apex configuration with resolved endpoints."""

    network_id: int
    http_base: str
    public_wss: str
    private_wss: str
    rest_paths: Dict[str, str]
    account: ApexAccount


def _load_raw_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _select_account(config: Dict[str, Any], label: Optional[str], index: Optional[int]) -> Dict[str, Any]:
    accounts = config.get("accounts", [])
    if not accounts:
        raise ValueError("No accounts defined in omni configuration")

    if label:
        for item in accounts:
            if item.get("label") == label:
                return item
        raise ValueError(f"Account label '{label}' not found in omni configuration")

    if index is not None:
        if index < 0 or index >= len(accounts):
            raise IndexError(f"Account index {index} out of range (total {len(accounts)})")
        return accounts[index]

    return accounts[0]


def load_apex_config(
    *,
    config_path: Optional[Path] = None,
    account_label: Optional[str] = None,
    account_index: Optional[int] = None,
) -> ApexConfig:
    """Load Omni endpoints and credentials for the requested account.

    Args:
        config_path: Optional override for the omni configuration JSON path.
        account_label: Select account by label; takes precedence over index.
        account_index: Select account by position when label not provided.

    Returns:
        ApexConfig containing resolved endpoints and the chosen credentials.
    """

    raw_config = _load_raw_config(config_path)
    network = raw_config.get("network", {})
    network_id = int(network.get("network_id", 9))

    endpoint_meta = NETWORK_ENDPOINTS.get(network_id)
    if not endpoint_meta:
        raise ValueError(f"Unsupported Omni network id: {network_id}")

    account_data = _select_account(raw_config, account_label, account_index)
    account = ApexAccount(
        label=account_data.get("label", ""),
        ethereum_address=account_data.get("ethereumAddress", ""),
        account_id=account_data.get("accountId", ""),
        sub_account_id=account_data.get("subAccountId", ""),
        api_key=account_data.get("apiKey", {}),
        zk=account_data.get("zk", {}),
    )

    return ApexConfig(
        network_id=network_id,
        http_base=endpoint_meta["http_base"],
        public_wss=endpoint_meta["public_wss"],
        private_wss=endpoint_meta["private_wss"],
        rest_paths=REST_API_PATHS,
        account=account,
    )


__all__ = [
    "ApexConfig",
    "ApexAccount",
    "NETWORK_ENDPOINTS",
    "REST_API_PATHS",
    "load_apex_config",
]
