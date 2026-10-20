import dataclasses
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trading import config, mercado, simulador
from trading.mercado import Ejecucion, Token, comprar, generar_tokens, vender
from trading.modelos import Candidato, Posicion
from trading.seguridad import revisar
from radar.scoring import evaluate

CFG = config.cargar()


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def sim(self, semilla=7, cfg=CFG, parar=None, tokens=60):
        return simulador.Simulador(cfg, semilla, tokens, self.tmp / f"diario-{semilla}",
                                   ruta_parar=parar or self.tmp / "PARAR.txt")


def token(destino="sano", liquidez=50_000, cadena="solana"):
    t = generar_tokens(random.Random(1), 1, 0)[0]
    return dataclasses.replace(t, destino=destino, liquidez=liquidez, cadena=cadena, precio=0.001)


class ConfigTest(Tmp):
    def escribir(self, texto):
        ruta = self.tmp / "limites.toml"
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def test_config_del_proyecto_es_valida_y_en_sombra(self):
        self.assertEqual(CFG.modo, "sombra")

    def test_modo_raro_se_trata_como_sombra(self):
        original = (config.RUTA_CONFIG).read_text(encoding="utf-8")
        ruta = self.escribir(original.replace('modo = "sombra"', 'modo = "turbo"'))
        self.assertEqual(config.cargar(ruta).modo, "sombra")

    def test_falta_un_limite_no_se_opera(self):
        original = (config.RUTA_CONFIG).read_text(encoding="utf-8")
        ruta = self.escribir(original.replace("max_por_dia_usd", "#max_por_dia_usd"))
        with self.assertRaises(config.ConfigError):
            config.cargar(ruta)

    def test_limite_negativo_no_se_opera(self):
        original = (config.RUTA_CONFIG).read_text(encoding="utf-8")
        ruta = self.escribir(original.replace("max_por_operacion_usd = 10", "max_por_operacion_usd = -5"))
        with self.assertRaises(config.ConfigError):
            config.cargar(ruta)


class PararTest(Tmp):
    def test_parar_al_inicio_no_opera_nada(self):
        parar = self.tmp / "PARAR.txt"
        parar.write_text("")
        s = self.sim(parar=parar)
        texto = s.correr()
        self.assertEqual(s.posiciones, [])
        self.assertEqual(s.parado_en, "00:00")
        self.assertIn("PARAR.txt", texto)

    def test_parar_a_mitad_frena_las_siguientes_operaciones(self):
        parar = self.tmp / "PARAR.txt"
        original = simulador.comprar

        def comprar_y_pulsar_parar(*a, **k):
            ej = original(*a, **k)
            if ej.ok:
                parar.write_text("")
            return ej

        with mock.patch.object(simulador, "comprar", comprar_y_pulsar_parar):
            s = self.sim(parar=parar)
            s.correr()
        self.assertEqual(len(s.posiciones), 1)
        self.assertFalse(s.posiciones[0].cerrada)  # ni siquiera vende tras PARAR
        self.assertIsNotNone(s.parado_en)


class LimitesTest(Tmp):
    def test_limites_por_operacion_y_por_dia_en_muchos_dias(self):
        for semilla in range(30):
            s = self.sim(semilla)
            s.correr()
            self.assertTrue(all(p.compra.usd <= CFG.max_por_operacion + 1e-9 for p in s.posiciones))
            self.assertLessEqual(s.gastado_hoy, CFG.max_por_dia + 1e-9)

    def test_limite_por_wallet_recorta_el_monto(self):
        cfg = dataclasses.replace(CFG, max_por_wallet=25, max_por_dia=1000)
        s = self.sim(cfg=cfg)
        cand = Candidato(token(), evaluate(token().par), "00:00", 0.001)
        s.posiciones = [Posicion(cand, Ejecucion(True, usd=20, cantidad=1), "00:00", "")]
        monto, nota = s._monto_permitido()
        self.assertAlmostEqual(monto, 5)
        self.assertIn("wallet", nota)


class MercadoTest(unittest.TestCase):
    def test_honeypot_deja_comprar_pero_no_vender(self):
        rng = random.Random(0)
        t = token("honeypot")
        with mock.patch.object(mercado, "PROB_FALLO_RED", 0):
            self.assertTrue(comprar(rng, t, 10, 5).ok)
            venta = vender(rng, t, 1000, 100)
        self.assertFalse(venta.ok)
        self.assertTrue(venta.honeypot)
        self.assertGreater(venta.comision_red, 0)

    def test_slippage_crece_con_el_tamano_y_puede_cancelar(self):
        with mock.patch.object(mercado, "PROB_FALLO_RED", 0):
            chico = comprar(random.Random(0), token(liquidez=1_000_000), 10, 100)
            grande = comprar(random.Random(0), token(liquidez=2_000), 500, 100)
            cancelada = comprar(random.Random(0), token(liquidez=2_000), 500, 5)
        self.assertLess(chico.slippage_pct, grande.slippage_pct)
        self.assertGreater(grande.precio, 0.001)  # al comprar, el precio empeora
        self.assertFalse(cancelada.ok)
        self.assertGreater(cancelada.comision_red, 0)  # la comisión se paga igual

    def test_rug_desploma_precio_y_liquidez(self):
        t = dataclasses.replace(token("rug"), paso_lanzamiento=0, paso_rug=1)
        precio, liq = t.precio, t.liquidez
        t.avanzar(1, random.Random(0))
        self.assertTrue(t.rugeado)
        self.assertLess(t.precio, precio * 0.1)
        self.assertLess(t.liquidez, liq * 0.05)


class SeguridadTest(unittest.TestCase):
    def test_dato_de_wallets_faltante_rechaza(self):
        t = token()
        billeteras = {"top10_pct": 20, "creador_pct": 1, "liquidez_bloqueada": None, "wallets_coordinadas": 0}
        motivos = revisar(evaluate(t.par), billeteras, dataclasses.replace(CFG, riesgo_maximo=100))
        self.assertTrue(any("ante la duda" in m for m in motivos))


class DiarioTest(Tmp):
    def test_cada_operacion_y_rechazo_tiene_autopsia_y_hay_resumen(self):
        s = self.sim(semilla=3)
        s.correr()
        carpeta = self.tmp / "diario-3"
        archivos = [p.name for p in carpeta.iterdir()]
        self.assertIn("RESUMEN.md", archivos)
        self.assertEqual(sum("_operacion" in a for a in archivos), len(s.posiciones))
        self.assertEqual(sum("_rechazada" in a for a in archivos), len(s.rechazos))
        self.assertEqual(sum("_fallida" in a for a in archivos), len(s.fallidas))
        texto = (carpeta / archivos[0]).read_text(encoding="utf-8")
        for seccion in ("## Qué vio", "## Qué decidió", "## Qué resultó"):
            self.assertIn(seccion, texto)

    def test_misma_semilla_mismo_dia(self):
        a = self.sim(semilla=11).correr()
        b = simulador.Simulador(CFG, 11, 60, self.tmp / "otra", ruta_parar=self.tmp / "PARAR.txt").correr()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
