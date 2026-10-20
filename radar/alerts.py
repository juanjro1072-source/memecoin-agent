"""Formateo de alertas y envío a consola, Telegram y/o Discord."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

from .scoring import Verdict


def bar(value: int, width: int = 10) -> str:
    filled = round(value / 100 * width)
    return "█" * filled + "░" * (width - filled)


def format_verdict(v: Verdict, reason: str = "") -> str:
    s = v.snap
    lines = [
        f"{v.archetype}  ${s.symbol} ({s.name}) · {s.chain}" + (f"  [{reason}]" if reason else ""),
        f"  HYPE   {bar(v.hype)} {v.hype:>3}",
        f"  RIESGO {bar(v.risk)} {v.risk:>3}",
        f"  precio ${s.price_usd:.8g} · liquidez ${s.liquidity_usd:,.0f} · FDV ${s.fdv:,.0f}",
    ]
    if v.hype_reasons:
        lines.append("  🔥 " + "; ".join(v.hype_reasons))
    for f in v.risk_flags:
        lines.append(f"  ⚠️  {f}")
    if s.url:
        lines.append(f"  {s.url}")
    return "\n".join(lines)


def format_row(v: Verdict) -> str:
    s = v.snap
    return f"{v.archetype:<11} ${s.symbol:<10} hype {v.hype:>3}  riesgo {v.risk:>3}  {s.chain}"


def _post(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15).close()


def send(text: str) -> None:
    """Imprime siempre; además envía a Telegram/Discord si están configurados."""
    print(text + "\n", flush=True)

    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            _post(
                f"https://api.telegram.org/bot{urllib.parse.quote(token, safe=':')}/sendMessage",
                {"chat_id": chat, "text": text, "disable_web_page_preview": True},
            )
        except Exception as e:  # una alerta fallida no debe tumbar el radar
            print(f"[telegram] no se pudo enviar: {e}", file=sys.stderr)

    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook:
        try:
            _post(webhook, {"content": f"```\n{text[:1900]}\n```"})
        except Exception as e:
            print(f"[discord] no se pudo enviar: {e}", file=sys.stderr)
