import csv
import dataclasses
import gzip
import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

from trading import config, laboratorio
from trading.simulador import Mono, Simulador

CFG = config.cargar()
REJILLA_MINI = {"hype_minimo": (50, 60), "riesgo_maximo": (40,), "tomar_ganancia_pct": (50,), "cortar_perdida_pct": (25,)}


class LaboratorioTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.enterContext(mock.patch.object(laboratorio, "RAIZ", self.raiz))
        self.enterContext(mock.patch.object(laboratorio, "REJILLA", REJILLA_MINI))

    def correr(self, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return laboratorio.main(["--dias", "6", "--entrenamiento", "4", "--monos", "2", *args])

    def carpeta(self):
        return next((self.raiz / "informes").iterdir())

    def test_no_modifica_limites_toml(self):
        antes = laboratorio.huella(config.RUTA_CONFIG)
        self.assertEqual(self.correr(), 0)
        self.assertEqual(laboratorio.huella(config.RUTA_CONFIG), antes)
        self.assertIn("No se modificó `limites.toml`", (self.carpeta() / "INFORME.md").read_text(encoding="utf-8"))

    def test_los_dias_de_validacion_no_se_usan_para_entrenar(self):
        self.correr()
        with gzip.open(self.carpeta() / "registro_compacto.csv.gz", "rt", encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        entrenamiento = {int(r["semilla"]) for r in filas if r["fase"] == "entrenamiento"}
        validacion = {int(r["semilla"]) for r in filas if r["fase"] == "validacion"}
        self.assertTrue(entrenamiento <= {0, 1, 2, 3})
        self.assertTrue(validacion <= {4, 5})

    def test_autopsias_completas_solo_en_validacion(self):
        self.correr()
        val = self.carpeta() / "validacion"
        self.assertTrue(any(val.rglob("RESUMEN.md")))
        fuera = [p for p in self.carpeta().rglob("*.md") if val not in p.parents and p.name != "INFORME.md"]
        self.assertEqual(fuera, [])

    def test_parar_detiene_el_laboratorio(self):
        llamadas = iter([False] * 5 + [True] * 10_000)
        with mock.patch.object(laboratorio, "hay_que_parar", lambda: next(llamadas)):
            self.assertEqual(self.correr(), 1)
        self.assertFalse((self.carpeta() / "INFORME.md").exists())


class ComparacionJustaTest(unittest.TestCase):
    def test_mismo_dia_mismo_mercado_para_cualquier_estrategia(self):
        otra = dataclasses.replace(CFG, hype_minimo=50, tomar_ganancia_pct=80)
        sims = [Simulador(CFG, 5, 60, None), Simulador(otra, 5, 60, None), Mono(CFG, 5, 60, None)]
        for s in sims:
            s.correr()
        precios = [[t.precio for t in s.tokens] for s in sims]
        self.assertEqual(precios[0], precios[1])
        self.assertEqual(precios[0], precios[2])

    def test_el_mono_no_usa_radar_ni_revision(self):
        compras = []
        for semilla in range(10):
            mono = Mono(CFG, semilla, 60, None)
            mono.correr()
            self.assertFalse([r for r in mono.rechazos if r[1] == "seguridad"])
            compras += mono.posiciones
        self.assertTrue(any(p.cand.veredicto.hype < CFG.hype_minimo for p in compras))
        self.assertTrue(any(p.cand.token.es_estafa for p in compras))


if __name__ == "__main__":
    unittest.main()
