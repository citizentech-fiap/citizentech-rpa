"""Regressões de movimentação segura e persistência sem regravação."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from robo.collector import _Cache, _escrever_atomico
from run_robot import _mover_pedido, _salvar_registry


class TestPersistencia(unittest.TestCase):
    def test_anexos_invalidos_e_duplicados(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "inbox"
            (base / "anexos").mkdir(parents=True)
            externo = Path(tmp) / "externo.txt"
            externo.write_text("não mover", encoding="utf-8")
            for malformado in (False, True):
                src = base / "REQ-1.json"
                anexo = base / "anexos/REQ-1_cpf.txt"
                anexo.write_text("DOCUMENTO FICTÍCIO - USO ACADÊMICO", encoding="utf-8")
                src.write_text("{ inválido" if malformado else json.dumps({
                    "anexos": ["anexos/REQ-1_cpf.txt", "../externo.txt"]}), encoding="utf-8")
                destino = Path(tmp) / ("failed" if malformado else "processed")
                _mover_pedido(src, base, destino)
                self.assertTrue((destino / "anexos/REQ-1_cpf.txt").exists())
                self.assertTrue((destino / src.name).exists())
                self.assertFalse(anexo.exists())
                self.assertTrue(externo.exists())

    def test_registry_atomico_preserva_anterior_em_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "registry.json"
            _salvar_registry(arquivo, {"primeiro": {"run_id": "1"}})
            anterior = arquivo.read_bytes()
            with patch.object(Path, "replace", side_effect=OSError("falha simulada")):
                with self.assertRaises(OSError):
                    _salvar_registry(arquivo, {"segundo": {"run_id": "2"}})
            self.assertEqual(arquivo.read_bytes(), anterior)
            _salvar_registry(arquivo, {"segundo": {"run_id": "2"}})
            self.assertIn("segundo", json.loads(arquivo.read_text(encoding="utf-8")))

    def test_conteudo_igual_nao_e_regravado(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "corpus.jsonl"
            _escrever_atomico(arquivo, "conteúdo\n")
            with patch("robo.collector.os.replace") as substituir:
                _escrever_atomico(arquivo, "conteúdo\n")
                substituir.assert_not_called()
            cache = _Cache(Path(tmp) / "cache")
            cache.salvar("teste", "https://exemplo.test", "html", {"texto": "igual"}, "api", "1", "data1")
            antes = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in cache.pasta.iterdir()}
            cache.salvar("teste", "https://exemplo.test", "html", {"texto": "igual"}, "api", "1", "data2")
            self.assertEqual(antes, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in cache.pasta.iterdir()})
