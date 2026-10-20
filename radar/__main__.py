"""Línea de comandos del radar.

    python -m radar scan            # una pasada contra DexScreener en vivo
    python -m radar scan --demo     # datos de ejemplo, sin internet
    python -m radar watch --every 120 --chain solana
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import alerts, dexscreener
from .scoring import ARCHETYPES, evaluate
from .state import AlertMemory

FIXTURE = Path(__file__).parent / "fixtures" / "demo_pairs.json"


def load_demo_pairs() -> list[dict]:
    pairs = json.loads(FIXTURE.read_text())
    now_ms = time.time() * 1000
    for p in pairs:
        p["pairCreatedAt"] = now_ms - p.pop("_age_minutes") * 60_000
    return pairs


def scan_once(args, memory: AlertMemory) -> int:
    try:
        pairs = load_demo_pairs() if args.demo else dexscreener.discover(set(args.chain or []) or None, args.limit)
    except OSError as e:
        print(f"No pude hablar con DexScreener: {e}", file=sys.stderr)
        return 0

    verdicts = sorted((evaluate(p) for p in pairs), key=lambda v: v.hype - v.risk, reverse=True)
    if args.all:
        print("\n".join(map(alerts.format_row, verdicts)) + "\n")
    sent = 0
    for v in verdicts:
        is_gem = v.hype >= args.min_hype and v.risk <= args.max_risk
        is_trap = args.warn_traps and v.archetype in (ARCHETYPES["CASINO"], ARCHETYPES["TRAMPA"])
        if not (is_gem or is_trap):
            continue
        reason = memory.should_alert(v.snap.key, v.hype)
        if reason is None:
            continue
        if is_trap and not is_gem:
            reason = "⛔ NO COMPRAR · " + reason
        alerts.send(alerts.format_verdict(v, reason))
        memory.remember(v.snap.key, v.hype)
        sent += 1
    memory.save()
    print(f"— {len(verdicts)} tokens analizados, {sent} alertas —", file=sys.stderr)
    return sent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="radar", description="Radar de memecoins: hype vs. riesgo.")
    parser.add_argument("mode", choices=["scan", "watch"], help="scan = una pasada; watch = en bucle")
    parser.add_argument("--demo", action="store_true", help="usar datos de ejemplo sin internet")
    parser.add_argument("--chain", action="append", help="filtrar por cadena (repetible): solana, base, ethereum, bsc…")
    parser.add_argument("--limit", type=int, default=60, help="máximo de tokens a revisar por pasada")
    parser.add_argument("--min-hype", type=int, default=60)
    parser.add_argument("--max-risk", type=int, default=40)
    parser.add_argument("--warn-traps", action="store_true", help="también avisar de CASINOS y TRAMPAS en tendencia")
    parser.add_argument("--all", action="store_true", help="mostrar además una tabla con todos los tokens")
    parser.add_argument("--every", type=int, default=120, help="segundos entre pasadas en modo watch")
    parser.add_argument("--state", default=".radar_state.json", help="archivo de memoria ('' para desactivar)")
    args = parser.parse_args(argv)

    memory = AlertMemory(Path(args.state) if args.state and not args.demo else None)
    if args.mode == "scan":
        scan_once(args, memory)
        return
    print(f"📡 Radar encendido: cada {args.every}s (Ctrl+C para parar)", file=sys.stderr)
    try:
        while True:
            scan_once(args, memory)
            time.sleep(args.every)
    except KeyboardInterrupt:
        print("\nRadar apagado.", file=sys.stderr)


if __name__ == "__main__":
    main()
