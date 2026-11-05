"""Contrato do gerador rural, separação de textos e localização reproduzível."""
from collections import Counter
import json
from pathlib import Path
import random
import tempfile
import unittest

import numpy as np

from robo.config import load_config
from scripts import gerar_dados_sinteticos as dados


class TestGerador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pasta = Path(cls.tmp.name)
        cls.labels = dados.gerar_teste(random.Random(dados.SEED), np.random.default_rng(dados.SEED), cls.pasta)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_treino_reproduzivel_e_catalogo(self):
        treino = dados.gerar_treino(random.Random(dados.SEED))
        self.assertEqual(treino, dados.gerar_treino(random.Random(dados.SEED)))
        sids = {s["id"] for s in load_config()["services"]} | {"fora_escopo"}
        self.assertEqual(Counter(sid for _, sid in treino), {sid: 40 for sid in sids})
        self.assertEqual(len(treino), len(set(treino)))
        textos_teste = [t for lista in dados.TEXTOS_TESTE.values() for t in lista]
        textos_teste += [t for _, _, t in dados.AMBIGUOS] + [t for t, _ in dados.FORA_ESCOPO_TESTE]
        self.assertFalse({dados.sem_acento(t).lower() for t, _ in treino}
                         & {dados.sem_acento(t).lower() for t in textos_teste})

    def test_proporcoes_documentos_e_localizacao(self):
        self.assertEqual(Counter(r["categoria"] for r in self.labels),
                         {"tipico": 25, "docs_faltando": 12, "ambiguo": 6,
                          "fora_escopo": 6, "ilegivel": 5, "invalido": 6})
        locais = {(r["municipio"], r["uf"], r["cod_ibge"]) for r in dados.carregar_municipios()}
        exigidos = {s["id"]: set(s["documentos_exigidos"]) for s in load_config()["services"]}
        tipos = set(load_config()["document_types"])
        cobertos = {"png": set(), "pdf": set()}
        for row in self.labels:
            with self.subTest(pedido=row["request_id"]):
                self.assertIn(tuple(row[c] for c in ("municipio", "uf", "cod_ibge")), locais)
                categoria = row["categoria"]
                esperado = {"tipico": "resolvido", "docs_faltando": "resolvido", "invalido": "invalido"}.get(categoria, "revisao_humana")
                self.assertEqual(row["resultado_esperado"], esperado)
                if categoria == "invalido":
                    continue
                req = json.loads((self.pasta / f"{row['request_id']}.json").read_text(encoding="utf-8"))
                self.assertEqual(tuple(req[c] for c in ("municipio", "uf", "cod_ibge")),
                                 tuple(row[c] for c in ("municipio", "uf", "cod_ibge")))
                presentes = set(filter(None, row["docs_presentes"].split(";")))
                self.assertTrue(presentes <= tipos)
                if categoria == "tipico":
                    self.assertTrue(exigidos[row["service_id"]] <= presentes)
                elif categoria == "docs_faltando":
                    self.assertTrue(exigidos[row["service_id"]] - presentes)
                elif categoria == "ilegivel":
                    self.assertEqual(len(row["docs_ilegiveis"].split(";")), 1)
                elif categoria == "ambiguo":
                    self.assertIn(row["observacao"].removeprefix("alternativa="), exigidos)
                for rel in req["anexos"]:
                    anexo = self.pasta / rel
                    self.assertTrue(anexo.is_file())
                    tipo = anexo.stem.removeprefix(row["request_id"] + "_")
                    cobertos[anexo.suffix[1:]].add(tipo)
        self.assertEqual(cobertos["pdf"], tipos)
        self.assertEqual(cobertos["png"], tipos)

    def test_sorteio_ponderado_reproduzivel(self):
        municipios = dados.carregar_municipios()
        r1, r2 = random.Random(dados.SEED), random.Random(dados.SEED)
        a = [dados.sortear_localizacao(r1, municipios) for _ in range(500)]
        self.assertEqual(a, [dados.sortear_localizacao(r2, municipios) for _ in range(500)])
        contagem = Counter(r["cod_ibge"] for r in a)
        self.assertGreater(contagem[municipios[0]["cod_ibge"]], contagem[municipios[-1]["cod_ibge"]] * 3)

    def test_cpf_invalido_e_documentos_do_config(self):
        rng = random.Random(dados.SEED)
        local = dados.sortear_localizacao(rng, dados.carregar_municipios())
        for _ in range(100):
            pessoa = dados.pessoa_ficticia(rng, local)
            numeros = [int(n) for n in pessoa["cpf"] if n.isdigit()]
            resto = sum(v * peso for v, peso in zip(numeros[:9], range(10, 1, -1))) * 10 % 11
            self.assertNotEqual(numeros[9], 0 if resto == 10 else resto)
        for tipo in load_config()["document_types"]:
            titulo, sub, campos = dados.conteudo_documento(tipo, pessoa, rng)
            self.assertTrue(titulo and sub and campos)


if __name__ == "__main__":
    unittest.main()
