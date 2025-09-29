"""ApeX Omni zkKeys payload signing helpers."""
from __future__ import annotations

import decimal
import hashlib
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from apexomni import zklink_sdk as sdk
from apexomni.starkex.order import DECIMAL_CONTEXT_ROUND_DOWN, DECIMAL_CONTEXT_ROUND_UP

from logger import setup_logger

logger = setup_logger("apex_zk_signer")

# ApeX requires client identifiers to be pseudo-random numeric strings.
_RANDOM_MAX = 10 ** 18
_MAX_UINT32 = (1 << 32) - 1
_MAX_UINT64 = (1 << 64) - 1


def _normalize_hex(value: str) -> str:
    if not value:
        return ""
    value = value.lower()
    return value[2:] if value.startswith("0x") else value


@dataclass
class OrderSigningContext:
    symbol_config: Dict[str, Any]
    asset_config: Dict[str, Any]
    account_id: str
    sub_account_id: str
    taker_fee_rate: str
    maker_fee_rate: str
    reduce_only: bool
    client_id: Optional[str] = None
    timestamp_seconds: Optional[int] = None


class ApexZkSigner:
    """Generate zkKeys payload signatures following the official SDK."""

    def __init__(
        self,
        *,
        seeds: str,
        l2_key: Optional[str] = None,
        pub_key_hash: Optional[str] = None,
        eth_address: Optional[str] = None,
    ) -> None:
        if not seeds:
            raise ValueError("zk seeds are required to initialise ApexZkSigner")

        self.eth_address = eth_address
        self._raw_seeds = seeds
        seeds_hex = _normalize_hex(seeds)
        try:
            self._seeds_bytes = bytes.fromhex(seeds_hex)
        except ValueError as exc:
            raise ValueError("zk seeds must be hex encoded") from exc

        self._signer = sdk.ZkLinkSigner().new_from_seed(self._seeds_bytes)
        self.l2_key = l2_key or self._signer.public_key()
        self.pub_key_hash = pub_key_hash or sdk.get_public_key_hash(self.l2_key)

    @staticmethod
    def generate_client_id() -> str:
        """Match the SDK's random numeric client id generation."""

        return str(random.randrange(_RANDOM_MAX, _RANDOM_MAX * 10))

    def derive_zk_keys(self) -> Dict[str, str]:
        """Expose derived keys for onboarding or external storage."""

        return {
            "seeds": self._raw_seeds,
            "l2Key": self.l2_key,
            "pubKeyHash": self.pub_key_hash,
        }

    def sign_order_payload(
        self,
        *,
        ctx: OrderSigningContext,
        side: str,
        size: str,
        price: str,
    ) -> Dict[str, Any]:
        """Return the zkKeys fields required when submitting an order."""

        symbol_cfg = ctx.symbol_config or {}
        asset_cfg = ctx.asset_config or {}

        if "l2PairId" not in symbol_cfg:
            raise ValueError("symbol_config missing l2PairId")
        if "decimals" not in asset_cfg:
            raise ValueError("asset_config missing decimals")
        tick_size = decimal.Decimal(str(symbol_cfg.get("tickSize", "0")))
        if tick_size == 0:
            raise ValueError("tickSize must be non-zero for zk signing")

        timestamp = ctx.timestamp_seconds or int(time.time())
        client_id = ctx.client_id or self.generate_client_id()

        size_decimal = decimal.Decimal(str(size))
        price_decimal = decimal.Decimal(str(price))

        if price_decimal / tick_size != int(price_decimal / tick_size):
            raise ValueError("价格需为tickSize整数倍以满足zk签名要求")

        decimals = int(asset_cfg.get("decimals", 0))
        scale = decimal.Decimal(10) ** decimals
        size_scaled = (size_decimal * scale).quantize(decimal.Decimal(0), rounding=decimal.ROUND_DOWN)
        price_scaled = (price_decimal * scale).quantize(decimal.Decimal(0), rounding=decimal.ROUND_DOWN)

        taker_fee_scaled = (
            decimal.Decimal(str(ctx.taker_fee_rate)) * decimal.Decimal(10000)
        ).quantize(decimal.Decimal(0), rounding=decimal.ROUND_UP)
        maker_fee_scaled = (
            decimal.Decimal(str(ctx.maker_fee_rate)) * decimal.Decimal(10000)
        ).quantize(decimal.Decimal(0), rounding=decimal.ROUND_UP)

        nonce_hash = hashlib.sha256(client_id.encode("utf-8")).hexdigest()
        nonce_int = int(nonce_hash, 16)
        slot_id = (nonce_int % _MAX_UINT64) // _MAX_UINT32
        nonce = nonce_int % _MAX_UINT32
        account_id = int(ctx.account_id) % _MAX_UINT32

        builder = sdk.ContractBuilder(
            int(account_id),
            int(ctx.sub_account_id),
            int(slot_id),
            int(nonce),
            int(symbol_cfg["l2PairId"]),
            str(size_scaled),
            str(price_scaled),
            side.upper() == "BUY",
            int(taker_fee_scaled),
            int(maker_fee_scaled),
            bool(ctx.reduce_only),
        )

        contract = sdk.Contract(builder)
        signature = self._signer.sign_musig(contract.get_bytes()).signature

        expiration_seconds = timestamp + 28 * 24 * 3600
        expiration_ms = expiration_seconds * 1000

        if side.upper() == "BUY":
            human_cost = DECIMAL_CONTEXT_ROUND_UP.multiply(size_decimal, price_decimal)
            fee = DECIMAL_CONTEXT_ROUND_UP.multiply(human_cost, decimal.Decimal(str(ctx.taker_fee_rate)))
        else:
            human_cost = DECIMAL_CONTEXT_ROUND_DOWN.multiply(size_decimal, price_decimal)
            fee = DECIMAL_CONTEXT_ROUND_DOWN.multiply(human_cost, decimal.Decimal(str(ctx.taker_fee_rate)))

        limit_fee = DECIMAL_CONTEXT_ROUND_UP.quantize(
            decimal.Decimal(fee),
            decimal.Decimal("0.000001"),
        )

        return {
            "clientId": client_id,
            "signature": signature,
            "expiration": expiration_ms,
            "limitFee": str(limit_fee),
        }


def create_apex_zk_signer(
    zk_config: Dict[str, Any],
    eth_address: Optional[str] = None,
) -> Optional[ApexZkSigner]:
    """Factory helper to build a signer from omni_config credentials."""

    if not zk_config:
        logger.warning("缺少zk配置，无法创建ZK签名器")
        return None

    seeds = zk_config.get("seeds")
    if not seeds:
        logger.warning("zk配置中缺少seeds")
        return None

    try:
        signer = ApexZkSigner(
            seeds=seeds,
            l2_key=zk_config.get("l2Key"),
            pub_key_hash=zk_config.get("pubKeyHash"),
            eth_address=eth_address,
        )
        logger.info("ZK签名器创建成功")
        return signer
    except Exception as exc:
        logger.error(f"创建ZK签名器失败: {exc}")
        return None


class ApexZkSignerMock:
    """Simple mock used for tests without linking the native SDK."""

    def __init__(self, client_id_prefix: str = "mock"):  # pragma: no cover - dev helper
        self._prefix = client_id_prefix

    def derive_zk_keys(self) -> Dict[str, str]:  # pragma: no cover - dev helper
        return {"seeds": "0x0", "l2Key": "0x0", "pubKeyHash": "0x0"}

    def sign_order_payload(self, *, ctx: OrderSigningContext, side: str, size: str, price: str) -> Dict[str, Any]:
        client_id = f"{self._prefix}-{int(time.time()*1000)}"
        return {
            "clientId": client_id,
            "signature": "0x" + "f" * 128,
            "expiration": (int(time.time()) + 60) * 1000,
            "limitFee": "0.000001",
        }
