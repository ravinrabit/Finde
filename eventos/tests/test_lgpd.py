import json
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from ..models import AceiteDeTermos, Evento, Favorito, Ingresso, PerfilUsuario, Produtor
from ..services import lgpd
from .base import criar_evento, criar_usuario


def _imagem_valida(nome="foto.png"):
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(nome, buffer.read(), content_type="image/png")


def _imagem_bomba_de_descompressao(nome="bomba.png"):
    # PNG minúsculo que declara dimensões gigantes (60000x60000px) no
    # cabeçalho IHDR sem ter pixel nenhum de verdade — faz o Pillow levantar
    # Image.DecompressionBombError já na abertura, antes de decodificar.
    import struct
    import zlib

    def bloco(tag, dados):
        return (
            struct.pack(">I", len(dados))
            + tag
            + dados
            + struct.pack(">I", zlib.crc32(tag + dados) & 0xFFFFFFFF)
        )

    assinatura = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 60000, 60000, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00" * 3)
    png = assinatura + bloco(b"IHDR", ihdr) + bloco(b"IDAT", idat) + bloco(b"IEND", b"")
    return SimpleUploadedFile(nome, png, content_type="image/png")


class ConsentimentoTests(TestCase):
    def test_cadastro_registra_o_aceite(self):
        self.client.post(
            reverse("cadastro"),
            {
                "full_name": "Maria da Silva",
                "email": "maria@exemplo.test",
                "password1": "senha-bem-forte-2026",
                "password2": "senha-bem-forte-2026",
                "terms": "on",
            },
        )
        aceite = AceiteDeTermos.objects.get()
        self.assertEqual(aceite.usuario.email, "maria@exemplo.test")
        self.assertEqual(aceite.versao_termos, lgpd.VERSAO_TERMOS)

    def test_cadastro_sem_aceitar_termos_e_recusado(self):
        resposta = self.client.post(
            reverse("cadastro"),
            {
                "full_name": "Maria da Silva",
                "email": "maria2@exemplo.test",
                "password1": "senha-bem-forte-2026",
                "password2": "senha-bem-forte-2026",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(User.objects.filter(email="maria2@exemplo.test").exists())


class ExportacaoTests(TestCase):
    def setUp(self):
        self.pessoa = criar_usuario("titular@exemplo.test")
        self.evento = criar_evento(criado_por=self.pessoa)
        Ingresso.objects.create(usuario=self.pessoa, evento=self.evento)
        Favorito.objects.create(usuario=self.pessoa, evento=self.evento)
        self.client.force_login(self.pessoa)

    def test_exportacao_traz_tudo(self):
        dados = lgpd.exportar_dados(self.pessoa)
        self.assertEqual(dados["conta"]["email"], "titular@exemplo.test")
        self.assertEqual(len(dados["ingressos"]), 1)
        self.assertEqual(len(dados["favoritos"]), 1)
        self.assertEqual(len(dados["eventos_publicados"]), 1)

    def test_exportacao_nao_inclui_senha(self):
        bruto = json.dumps(lgpd.exportar_dados(self.pessoa))
        self.assertNotIn("password", bruto.lower())
        self.assertNotIn(self.pessoa.password, bruto)

    def test_view_devolve_json_para_download(self):
        resposta = self.client.get(reverse("exportar_meus_dados"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("application/json", resposta["Content-Type"])
        self.assertIn("attachment", resposta["Content-Disposition"])
        json.loads(resposta.content)

    def test_exportacao_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("exportar_meus_dados"))
        self.assertEqual(resposta.status_code, 302)


class ExclusaoTests(TestCase):
    def setUp(self):
        self.pessoa = criar_usuario("apagar@exemplo.test")
        self.evento = criar_evento(criado_por=self.pessoa, status=Evento.Status.PUBLICADO)
        Ingresso.objects.create(usuario=self.pessoa, evento=self.evento)
        Favorito.objects.create(usuario=self.pessoa, evento=self.evento)
        self.client.force_login(self.pessoa)

    def test_conta_e_apagada_de_verdade(self):
        lgpd.excluir_conta(self.pessoa)
        self.assertFalse(User.objects.filter(email="apagar@exemplo.test").exists())

    def test_ingressos_e_favoritos_somem(self):
        lgpd.excluir_conta(self.pessoa)
        self.assertEqual(Ingresso.objects.count(), 0)
        self.assertEqual(Favorito.objects.count(), 0)

    def test_eventos_publicados_ficam_sem_autor(self):
        lgpd.excluir_conta(self.pessoa)
        self.evento.refresh_from_db()
        self.assertIsNone(self.evento.criado_por)
        self.assertEqual(self.evento.status, Evento.Status.PUBLICADO)

    def test_produtor_e_desvinculado_mas_preservado(self):
        Produtor.objects.create(nome="Produtora da pessoa", user=self.pessoa)
        lgpd.excluir_conta(self.pessoa)
        produtor = Produtor.objects.get()
        self.assertIsNone(produtor.user_id)

    def test_perfil_e_apagado_junto_com_a_conta(self):
        PerfilUsuario.objects.create(usuario=self.pessoa)
        lgpd.excluir_conta(self.pessoa)
        self.assertEqual(PerfilUsuario.objects.count(), 0)

    def test_view_exige_senha_correta(self):
        resposta = self.client.post(
            reverse("excluir_minha_conta"), {"senha": "errada", "confirmacao": "EXCLUIR"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.pessoa.pk).exists())

    def test_view_exige_a_palavra_de_confirmacao(self):
        resposta = self.client.post(
            reverse("excluir_minha_conta"), {"senha": "senha-forte-123", "confirmacao": "sim"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.pessoa.pk).exists())

    def test_view_apaga_com_senha_e_confirmacao(self):
        resposta = self.client.post(
            reverse("excluir_minha_conta"),
            {"senha": "senha-forte-123", "confirmacao": "EXCLUIR"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.pessoa.pk).exists())


class PaginasDePrivacidadeTests(TestCase):
    def test_pagina_de_dados_exige_login(self):
        self.assertEqual(self.client.get(reverse("minha_privacidade")).status_code, 302)

    def test_pagina_de_dados_responde_logado(self):
        self.client.force_login(criar_usuario("logada@exemplo.test"))
        self.assertEqual(self.client.get(reverse("minha_privacidade")).status_code, 200)

    def test_politica_aponta_para_a_pagina_de_dados(self):
        resposta = self.client.get(reverse("privacidade"))
        self.assertContains(resposta, reverse("minha_privacidade"))

    def test_existe_canal_de_contato(self):
        resposta = self.client.get(reverse("contato"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "mailto:")


class PerfilTests(TestCase):
    def setUp(self):
        self.pessoa = criar_usuario("perfil@exemplo.test")
        self.client.force_login(self.pessoa)

    def test_pagina_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("perfil"))
        self.assertEqual(resposta.status_code, 302)

    def test_pagina_responde_logado(self):
        resposta = self.client.get(reverse("perfil"))
        self.assertEqual(resposta.status_code, 200)

    def test_atualiza_o_nome(self):
        self.client.post(reverse("perfil"), {"full_name": "Maria Nova Silva"})
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.first_name, "Maria")
        self.assertEqual(self.pessoa.last_name, "Nova Silva")

    def test_nome_curto_e_recusado(self):
        resposta = self.client.post(reverse("perfil"), {"full_name": "Jo"})
        self.assertEqual(resposta.status_code, 200)
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.first_name, "")

    def test_envia_foto_de_perfil(self):
        self.client.post(
            reverse("perfil"),
            {"full_name": "Maria Silva", "foto": _imagem_valida()},
        )
        self.pessoa.refresh_from_db()
        self.assertTrue(self.pessoa.perfil.foto)

    def test_cria_o_perfil_na_primeira_visita(self):
        self.assertFalse(PerfilUsuario.objects.filter(usuario=self.pessoa).exists())
        self.client.get(reverse("perfil"))
        self.assertTrue(PerfilUsuario.objects.filter(usuario=self.pessoa).exists())

    def test_pagina_nao_mostra_marcacao_crua_do_widget_padrao_quando_ja_tem_foto(self):
        perfil = PerfilUsuario.objects.create(usuario=self.pessoa, foto=_imagem_valida())
        resposta = self.client.get(reverse("perfil"))
        conteudo = resposta.content.decode()
        self.assertNotIn("Atualmente:", conteudo)
        self.assertNotIn("Limpar", conteudo)
        self.assertIn(perfil.foto.url, conteudo)

    def test_remove_a_foto_de_perfil(self):
        PerfilUsuario.objects.create(usuario=self.pessoa, foto=_imagem_valida())
        self.client.post(reverse("perfil"), {"acao": "remover_foto"})
        self.pessoa.refresh_from_db()
        self.assertFalse(self.pessoa.perfil.foto)

    def test_foto_com_dimensoes_declaradas_absurdas_e_recusada_sem_quebrar(self):
        resposta = self.client.post(
            reverse("perfil"),
            {"full_name": "Maria Silva", "foto": _imagem_bomba_de_descompressao()},
        )
        self.assertEqual(resposta.status_code, 200)
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=self.pessoa)
        self.assertFalse(perfil.foto)
