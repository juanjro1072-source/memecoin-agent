import copy
import tempfile
import time
import unittest
from pathlib import Path

from radar.__main__ import load_demo_pairs
from trading import config
from vivo.fuentes import normalizar_rugcheck
from vivo.observador import Observador

BUENAS = {"top10_pct": 20, "creador_pct": 1, "liquidez_bloqueada": True, "wallets_coordinadas": 0}


def par_solana(simbolo="CAPYX", indice=0, direccion=None, precio="0.004"):
    """Un par como los de DexScreener, a partir de los ejemplos del radar."""
    p = copy.deepcopy(load_demo_pairs()[indice])
    p["chainId"] = "solana"
    p["baseToken"] = {**p["baseToken"], "symbol": simbolo, "address": direccion or f"MINT{simbolo}"}
    p["pairAddress"] = f"PAR{simbolo}"
    p["dexId"] = "raydium"
    p["priceUsd"] = precio
    return p


class FuentesFalsas:
    def __init__(self, pares):
        self.pares = pares
        self.billeteras = BUENAS
        self.error_wallets = None
        self.consultas_wallets = []
        self.precios_actuales = {}  # token -> (precio, liquidez); ausente = el par desapareció

    def descubrir(self):
        return self.pares

    def wallets(self, cadena, token):
        self.consultas_wallets.append(token)
        if self.error_wallets:
            raise self.error_wallets
        return dict(self.billeteras), []

    def precios(self, cadena, tokens):
        salida = []
        for t in tokens:
            if t in self.precios_actuales:
                precio, liq = self.precios_actuales[t]
                salida.append({"baseToken": {"address": t}, "pairAddress": f"PAR{t[4:]}",
                               "priceUsd": str(precio), "liquidity": {"usd": liq}})
        return salida


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.t = time.time()
        self.mensajes = []

    def observador(self, pares):
        self.fuentes = FuentesFalsas(pares)
        return Observador(self.dir / "vivo", fuentes=self.fuentes, ruta_parar=self.dir / "PARAR.txt",
                          ahora=lambda: self.t, dormir=lambda s: None, salida=self.mensajes.append)


class DecisionTest(Base):
    def test_compra_guarda_precio_exacto_costos_y_autopsia(self):
        obs = self.observador([par_solana()])
        self.assertTrue(obs.ciclo())
        [r] = obs.db.todas()
        self.assertEqual(r["accion"], "compra")
        self.assertEqual(r["precio"], 0.004)
        self.assertAlmostEqual(r["momento"], self.t)
        self.assertGreater(r["precio_entrada"], r["precio"])  # slippage: compras más caro
        self.assertGreater(r["comision_red"], 0)
        self.assertGreater(r["comision_dex"], 0)
        texto = (obs.carpeta / r["archivo"]).read_text(encoding="utf-8")
        for seccion in ("## Qué vio", "## Qué decidió", "## Qué resultó", "Precio exacto al decidir"):
            self.assertIn(seccion, texto)
        self.assertTrue(any(obs.carpeta.glob("resumen_*.md")))

    def test_cada_token_se_decide_una_sola_vez(self):
        obs = self.observador([par_solana()])
        obs.ciclo()
        obs.ciclo()
        self.assertEqual(len(obs.db.todas()), 1)

    def test_si_rugcheck_falla_no_se_compra(self):
        obs = self.observador([par_solana()])
        self.fuentes.error_wallets = OSError("sin conexión")
        obs.ciclo()
        [r] = obs.db.todas()
        self.assertEqual(r["accion"], "rechazo")
        self.assertTrue(any("ante la duda" in m for m in r["motivos"]))

    def test_dato_de_wallet_faltante_no_se_compra(self):
        obs = self.observador([par_solana()])
        self.fuentes.billeteras = {**BUENAS, "wallets_coordinadas": None}
        obs.ciclo()
        self.assertEqual(obs.db.todas()[0]["accion"], "rechazo")

    def test_radar_riesgoso_se_rechaza_sin_consultar_rugcheck(self):
        obs = self.observador([par_solana("HAMLON", indice=2)])  # 🎰 CASINO: hype 93, riesgo 60
        obs.ciclo()
        [r] = obs.db.todas()
        self.assertEqual((r["accion"], r["tipo"]), ("rechazo", "seguridad"))
        self.assertEqual(self.fuentes.consultas_wallets, [])

    def test_limite_diario_de_limites_toml(self):
        cfg = config.cargar()
        pares = [par_solana(f"TOK{i}") for i in range(6)]
        obs = self.observador(pares)
        obs.ciclo()
        filas = obs.db.todas()
        compras = [r for r in filas if r["accion"] == "compra"]
        self.assertEqual(sum(r["monto"] for r in compras), cfg.max_por_dia)
        self.assertTrue(all(r["monto"] <= cfg.max_por_operacion for r in compras))
        self.assertTrue(any(r["tipo"] == "límites" for r in filas))

    def test_otras_cadenas_se_ignoran(self):
        p = par_solana()
        p["chainId"] = "base"
        obs = self.observador([p])
        obs.ciclo()
        self.assertEqual(obs.db.todas(), [])


class SeguimientoTest(Base):
    def test_precio_a_1h_y_24h_y_veredicto(self):
        obs = self.observador([par_solana()])
        obs.ciclo()
        self.fuentes.pares = []
        self.fuentes.precios_actuales["MINTCAPYX"] = (0.006, 200_000)
        self.t += 3600 + 60
        obs.ciclo()
        r = obs.db.todas()[0]
        self.assertEqual(r["precio_1h"], 0.006)
        self.assertIsNone(r["precio_24h"])
        self.assertGreater(r["valor_1h"], 0)
        self.fuentes.precios_actuales["MINTCAPYX"] = (0.008, 250_000)
        self.t += 86400
        obs.ciclo()
        r = obs.db.todas()[0]
        self.assertEqual(r["precio_24h"], 0.008)
        self.assertGreater(r["valor_24h"], r["monto"])  # el precio se duplicó: ganó
        texto = (obs.carpeta / r["archivo"]).read_text(encoding="utf-8")
        self.assertIn("✅ ganó", texto)

    def test_si_el_par_desaparece_vale_cero(self):
        obs = self.observador([par_solana()])
        obs.ciclo()
        self.fuentes.pares = []
        self.t += 86400 + 60  # el Mac estuvo dormido: se llenan 1 h y 24 h a la vez
        obs.ciclo()
        r = obs.db.todas()[0]
        self.assertEqual(r["valor_1h"], 0)
        self.assertEqual(r["valor_24h"], 0)
        texto = (obs.carpeta / r["archivo"]).read_text(encoding="utf-8")
        self.assertIn("desapareció", texto)
        self.assertIn("retraso", texto)


class PararTest(Base):
    def test_parar_antes_del_ciclo(self):
        obs = self.observador([par_solana()])
        (self.dir / "PARAR.txt").write_text("")
        self.assertFalse(obs.ciclo())
        self.assertEqual(obs.db.todas(), [])

    def test_parar_a_mitad_del_ciclo(self):
        obs = self.observador([par_solana("A"), par_solana("B"), par_solana("C")])
        original = obs.considerar

        def considerar_y_pulsar(*a):
            n = original(*a)
            (self.dir / "PARAR.txt").write_text("")
            return n

        obs.considerar = considerar_y_pulsar
        self.assertFalse(obs.ciclo())
        self.assertEqual(len(obs.db.todas()), 1)

    def test_correr_no_arranca_con_parar(self):
        (self.dir / "PARAR.txt").write_text("")
        self.assertEqual(self.observador([]).correr(30), 1)


class SoloLecturaTest(Base):
    def test_no_modifica_limites_toml(self):
        antes = config.RUTA_CONFIG.read_bytes()
        obs = self.observador([par_solana()])
        obs.ciclo()
        self.assertEqual(config.RUTA_CONFIG.read_bytes(), antes)


class RugCheckTest(unittest.TestCase):
    def informe(self, **cambios):
        d = {
            "creator": "CREADOR",
            "freezeAuthority": None,
            "mintAuthority": None,
            "graphInsidersDetected": 2,
            "knownAccounts": {"POOL": {"name": "Raydium", "type": "AMM"}},
            "markets": [{"lp": {"lpLockedPct": 100}}],
            "topHolders": [{"address": "POOL", "owner": "POOL", "pct": 40}]
                          + [{"address": f"H{i}", "owner": f"W{i}", "pct": 3} for i in range(12)]
                          + [{"address": "HC", "owner": "CREADOR", "pct": 2}],
        }
        d.update(cambios)
        return d

    def test_informe_normal(self):
        billeteras, extra = normalizar_rugcheck(self.informe())
        self.assertEqual(billeteras["top10_pct"], 30)  # sin contar el pool
        self.assertEqual(billeteras["creador_pct"], 2)
        self.assertTrue(billeteras["liquidez_bloqueada"])
        self.assertEqual(billeteras["wallets_coordinadas"], 2)
        self.assertEqual(extra, [])

    def test_fracciones_se_pasan_a_porcentaje(self):
        holders = [{"address": f"H{i}", "owner": f"W{i}", "pct": 0.05} for i in range(10)]
        billeteras, _ = normalizar_rugcheck(self.informe(topHolders=holders, creator="OTRO"))
        self.assertAlmostEqual(billeteras["top10_pct"], 50)
        self.assertAlmostEqual(billeteras["creador_pct"], 5)  # fuera del top: como mucho el menor

    def test_peligros_y_datos_faltantes(self):
        d = self.informe(freezeAuthority="ALGUIEN", rugged=True)
        del d["mintAuthority"]
        del d["graphInsidersDetected"]
        billeteras, extra = normalizar_rugcheck(d)
        self.assertIsNone(billeteras["wallets_coordinadas"])
        texto = " ".join(extra)
        self.assertIn("CONGELAR", texto)
        self.assertIn("RUGGED", texto)
        self.assertIn("mintAuthority", texto)

    def test_respuesta_rara(self):
        billeteras, extra = normalizar_rugcheck(["no", "es", "un", "dict"])
        self.assertTrue(all(v is None for v in billeteras.values()))
        self.assertTrue(extra)


if __name__ == "__main__":
    unittest.main()
