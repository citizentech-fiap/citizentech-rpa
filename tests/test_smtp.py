"""SMTP opcional sem conexões reais."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from robo import outputs


class TestSMTP(unittest.TestCase):
    def executar(self, enviar=True, falhar=False, tls=True):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(outputs, "path", return_value=Path(tmp)), \
                patch.object(outputs, "load_config", return_value={"email": {
                    "send": enviar, "host": "localhost", "port": 1025, "starttls": tls, "sender": "teste@example.test"}}), \
                patch.object(outputs, "env", side_effect=lambda chave: {"SMTP_USER": "usuario", "SMTP_PASSWORD": "senha"}[chave]), \
                patch.object(outputs.smtplib, "SMTP") as smtp:
            cliente = smtp.return_value.__enter__.return_value
            if falhar:
                cliente.send_message.side_effect = OSError("falha simulada")
            resultado = {}
            arquivo = outputs.write_eml(SimpleNamespace(request_id="REQ-TESTE", nome="Fulano Fictício", email="ficticio@example.test"),
                                        "Assunto", "Corpo", resultado)
            self.assertTrue(arquivo.exists())
            self.assertIn(b"teste@example.test", arquivo.read_bytes())
            if enviar:
                cliente.send_message.assert_called_once()
                cliente.login.assert_called_once_with("usuario", "senha")
                self.assertEqual(cliente.starttls.call_count, int(tls))
            else:
                smtp.assert_not_called()
            return resultado

    def test_desativado(self):
        self.assertEqual(self.executar(enviar=False)["status_email"], "rascunho")

    def test_sucesso(self):
        self.assertEqual(self.executar()["status_email"], "enviado")

    def test_sem_tls(self):
        self.assertEqual(self.executar(tls=False)["status_email"], "enviado")

    def test_falha_preserva_rascunho(self):
        self.assertEqual(self.executar(falhar=True), {"status_email": "falha", "erro_email": "OSError"})
