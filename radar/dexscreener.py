"""Cliente mínimo de la API pública de DexScreener (sin API key, sin dependencias)."""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict

BASE_URL = "https://api.dexscreener.com"
USER_AGENT = "memecoin-radar/0.1"
MAX_ADDRESSES_PER_CALL = 30  # límite de /tokens/v1


def _get(path: str):
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def latest_profiles() -> list[dict]:
    """Tokens que acaban de crear su perfil en DexScreener (señal de lanzamiento)."""
    return _get("/token-profiles/latest/v1") or []


def latest_boosts() -> list[dict]:
    """Tokens que están pagando 'boosts' para salir en tendencias."""
    return _get("/token-boosts/latest/v1") or []


def pairs_for_tokens(chain: str, addresses: list[str]) -> list[dict]:
    pairs: list[dict] = []
    for i in range(0, len(addresses), MAX_ADDRESSES_PER_CALL):
        chunk = ",".join(addresses[i : i + MAX_ADDRESSES_PER_CALL])
        pairs.extend(_get(f"/tokens/v1/{chain}/{chunk}") or [])
    return pairs


def discover(chains: set[str] | None = None, limit: int = 60) -> list[dict]:
    """Devuelve el par con más liquidez de cada token recién lanzado o en tendencia."""
    by_chain: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for item in latest_profiles() + latest_boosts():
        chain, addr = item.get("chainId"), item.get("tokenAddress")
        if not chain or not addr or (chain, addr) in seen:
            continue
        if chains and chain not in chains:
            continue
        seen.add((chain, addr))
        by_chain[chain].append(addr)
        if len(seen) >= limit:
            break

    best: dict[tuple[str, str], dict] = {}
    for chain, addresses in by_chain.items():
        for pair in pairs_for_tokens(chain, addresses):
            key = (chain, pair.get("baseToken", {}).get("address", ""))
            liq = (pair.get("liquidity") or {}).get("usd") or 0
            if key not in best or liq > ((best[key].get("liquidity") or {}).get("usd") or 0):
                best[key] = pair
    return list(best.values())
