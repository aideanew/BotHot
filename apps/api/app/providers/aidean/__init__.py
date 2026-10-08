"""Aidean 主平台防腐层（SSO / 钱包）。"""

from app.providers.aidean.client import AideanProviderClient, TokenPair, decode_id_token_payload

__all__ = ["AideanProviderClient", "TokenPair", "decode_id_token_payload"]
