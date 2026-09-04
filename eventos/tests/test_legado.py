"""Suíte original do projeto, preservada integralmente.

Estes 64 testes existiam antes da evolução e continuam sendo a rede de
segurança contra regressão: se um comportamento antigo quebrar, é aqui que
aparece. Só os imports mudaram de nível (o módulo virou pacote) e as chamadas
a `eventos.scraping` apontam para `eventos.ingestao`, que é o mesmo contrato
com o nome novo.

Os testes NOVOS estão nos outros módulos de eventos/tests/.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..constants import Categoria, Regiao
from ..models import Evento, Favorito, Ingresso


def criar_evento(**campos):
    padrao = {
        "nome": "Show de teste no Cerrado",
        "data": timezone.now() + timedelta(days=5),
        "local": "Clube do Choro",
        "categoria": Categoria.MUSICA,
        "regiao": Regiao.ASA_SUL,
        "preco": Decimal("50.00"),
    }
    return Evento.objects.create(**{**padrao, **campos})


# =========================
# MODELO
# =========================

class EventoModeloTests(TestCase):
    def test_slug_gerado_automaticamente(self):
        evento = criar_evento(nome="Festival do Cerrado 2026")
        self.assertEqual(evento.slug, "festival-do-cerrado-2026")

    def test_slug_duplicado_recebe_sufixo(self):
        criar_evento(nome="Mesmo Nome")
        segundo = criar_evento(nome="Mesmo Nome")
        self.assertEqual(segundo.slug, "mesmo-nome-2")

    def test_evento_gratuito_zera_o_preco(self):
        evento = criar_evento(gratuito=True, preco=Decimal("80.00"))
        self.assertIsNone(evento.preco)
        self.assertEqual(evento.preco_rotulo, "Gratuito")

    def test_rotulo_de_preco_formata_em_reais(self):
        evento = criar_evento(preco=Decimal("1250.50"))
        self.assertEqual(evento.preco_rotulo, "A partir de R$ 1.250,50")

    def test_preco_indefinido_nao_vira_zero(self):
        evento = criar_evento(preco=None)
        self.assertEqual(evento.preco_rotulo, "Valor a definir")

    def test_meia_entrada_e_metade_da_inteira(self):
        evento = criar_evento(preco=Decimal("99.00"))
        self.assertEqual(evento.valor_para(Ingresso.Tipo.MEIA), Decimal("49.50"))

    def test_evento_com_data_fim_futura_ainda_conta_como_visivel(self):
        criar_evento(
            data=timezone.now() - timedelta(hours=2),
            data_fim=timezone.now() + timedelta(hours=4),
        )
        self.assertEqual(Evento.objects.visiveis().count(), 1)

    def test_evento_passado_sai_das_listagens(self):
        criar_evento(data=timezone.now() - timedelta(days=3))
        self.assertEqual(Evento.objects.visiveis().count(), 0)

    def test_apenas_publicados_aparecem(self):
        criar_evento(status=Evento.Status.PENDENTE)
        criar_evento(status=Evento.Status.ARQUIVADO, nome="Outro")
        self.assertEqual(Evento.objects.visiveis().count(), 0)


# =========================
# LISTAGEM E FILTROS
# =========================

class ListagemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gratuito = criar_evento(
            nome="Sarau gratuito na Ceilândia", gratuito=True,
            preco=None, regiao=Regiao.CEILANDIA, categoria=Categoria.CULTURA,
        )
        cls.caro = criar_evento(
            nome="Show grande no Mané", preco=Decimal("300.00"),
            regiao=Regiao.PLANO_PILOTO, categoria=Categoria.SHOWS,
        )
        cls.barato = criar_evento(
            nome="Teatro em Taguatinga", preco=Decimal("30.00"),
            regiao=Regiao.TAGUATINGA, categoria=Categoria.TEATRO,
        )

    def resultados(self, **parametros):
        resposta = self.client.get(reverse("lista_eventos"), parametros)
        self.assertEqual(resposta.status_code, 200)
        return list(resposta.context["pagina"].object_list)

    def test_sem_filtros_lista_tudo(self):
        self.assertEqual(len(self.resultados()), 3)

    def test_filtro_por_categoria(self):
        self.assertEqual(self.resultados(categoria=Categoria.TEATRO), [self.barato])

    def test_filtro_por_regiao(self):
        self.assertEqual(self.resultados(regiao=Regiao.CEILANDIA), [self.gratuito])

    def test_filtro_de_gratuitos(self):
        self.assertEqual(self.resultados(preco="gratuito"), [self.gratuito])

    def test_filtro_por_faixa_de_preco(self):
        self.assertEqual(self.resultados(preco="ate-50"), [self.barato])
        self.assertEqual(self.resultados(preco="acima-150"), [self.caro])

    def test_busca_procura_no_local_e_no_nome(self):
        self.assertEqual(self.resultados(q="Mané"), [self.caro])
        self.assertEqual(self.resultados(q="sarau"), [self.gratuito])

    def test_ordenacao_por_preco_coloca_gratuito_primeiro(self):
        resultados = self.resultados(ordenar="preco")
        self.assertEqual(resultados[0], self.gratuito)
        self.assertEqual(resultados[-1], self.caro)

    def test_filtro_invalido_nao_derruba_os_filtros_validos(self):
        # O conjunto inteiro de filtros era descartado quando um só era inválido.
        self.assertEqual(
            self.resultados(categoria="nao-existe", regiao=Regiao.CEILANDIA),
            [self.gratuito],
        )

    def test_ordenacao_invalida_nao_derruba_o_filtro(self):
        self.assertEqual(
            self.resultados(ordenar="inventado", regiao=Regiao.TAGUATINGA),
            [self.barato],
        )

    def test_filtro_invalido_e_ignorado_em_vez_de_quebrar(self):
        resposta = self.client.get(reverse("lista_eventos"), {"categoria": "nao-existe"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(resposta.context["pagina"].object_list), 3)


# =========================
# PÁGINA DO EVENTO
# =========================

class DetalheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dono = User.objects.create_user("dono@teste.com", password="senha-forte-123")
        cls.outro = User.objects.create_user("outro@teste.com", password="senha-forte-123")

    def test_evento_publicado_e_publico(self):
        evento = criar_evento()
        self.assertEqual(self.client.get(evento.get_absolute_url()).status_code, 200)

    def test_url_antiga_por_id_redireciona_para_o_slug(self):
        evento = criar_evento()
        resposta = self.client.get(reverse("evento_por_id", args=[evento.pk]))
        self.assertRedirects(resposta, evento.get_absolute_url(), status_code=301)

    def test_pendente_e_invisivel_para_visitante(self):
        evento = criar_evento(status=Evento.Status.PENDENTE, criado_por=self.dono)
        self.assertEqual(self.client.get(evento.get_absolute_url()).status_code, 404)

    def test_pendente_e_visivel_para_o_dono(self):
        evento = criar_evento(status=Evento.Status.PENDENTE, criado_por=self.dono)
        self.client.force_login(self.dono)
        self.assertEqual(self.client.get(evento.get_absolute_url()).status_code, 200)

    def test_pendente_continua_invisivel_para_outro_usuario(self):
        evento = criar_evento(status=Evento.Status.PENDENTE, criado_por=self.dono)
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(evento.get_absolute_url()).status_code, 404)

    def test_relacionados_nao_puxam_eventos_sem_nada_em_comum(self):
        evento = criar_evento(nome="Sem classificação", categoria="", regiao="")
        criar_evento(nome="Outro sem classificação", categoria="", regiao="")
        resposta = self.client.get(evento.get_absolute_url())
        self.assertEqual(list(resposta.context["relacionados"]), [])

    def test_visualizacao_e_contabilizada(self):
        evento = criar_evento()
        self.client.get(evento.get_absolute_url())
        evento.refresh_from_db()
        self.assertEqual(evento.visualizacoes, 1)

    def test_slug_numerico_nao_colide_com_a_rota_por_id(self):
        evento = criar_evento(nome="2026")
        self.assertEqual(evento.slug, "evento-2026")
        self.assertEqual(self.client.get(evento.get_absolute_url()).status_code, 200)

    def test_dados_estruturados_escapam_fechamento_de_script(self):
        evento = criar_evento(nome="Festival </script><script>alert(1)</script>")
        resposta = self.client.get(evento.get_absolute_url())
        corpo = resposta.content.decode()
        self.assertNotIn("</script><script>alert(1)", corpo)
        self.assertIn("\\u003C/script\\u003E", corpo)

    def test_pagina_publica_dados_estruturados(self):
        evento = criar_evento()
        resposta = self.client.get(evento.get_absolute_url())
        self.assertContains(resposta, "application/ld+json")
        self.assertContains(resposta, "schema.org")


# =========================
# INGRESSOS
# =========================

class IngressoTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("pessoa@teste.com", password="senha-forte-123")
        self.evento = criar_evento(preco=Decimal("100.00"))

    def test_reserva_exige_login(self):
        url = reverse("reservar_ingresso", args=[self.evento.slug])
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta.url)

    def test_reserva_cria_um_ingresso_por_unidade(self):
        self.client.force_login(self.usuario)
        self.client.post(
            reverse("reservar_ingresso", args=[self.evento.slug]),
            {"tipo": "meia", "quantidade": 3},
        )
        ingressos = Ingresso.objects.filter(usuario=self.usuario)
        self.assertEqual(ingressos.count(), 3)
        self.assertEqual(ingressos.first().valor, Decimal("50.00"))

    def test_quantidade_e_limitada_a_dez(self):
        self.client.force_login(self.usuario)
        self.client.post(
            reverse("reservar_ingresso", args=[self.evento.slug]),
            {"tipo": "inteira", "quantidade": 999},
        )
        self.assertEqual(Ingresso.objects.count(), 10)

    def test_quantidade_invalida_nao_derruba_a_view(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(
            reverse("reservar_ingresso", args=[self.evento.slug]),
            {"tipo": "inteira", "quantidade": "abc"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Ingresso.objects.count(), 1)

    def test_nao_reserva_evento_passado(self):
        passado = criar_evento(nome="Já foi", data=timezone.now() - timedelta(days=1))
        self.client.force_login(self.usuario)
        resposta = self.client.post(
            reverse("reservar_ingresso", args=[passado.slug]), {"quantidade": 1}
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Ingresso.objects.count(), 0)

    def test_cancelamento_muda_o_status(self):
        ingresso = Ingresso.objects.create(
            usuario=self.usuario, evento=self.evento, valor=Decimal("100.00")
        )
        self.client.force_login(self.usuario)
        self.client.post(reverse("cancelar_ingresso", args=[ingresso.codigo]))
        ingresso.refresh_from_db()
        self.assertEqual(ingresso.status, Ingresso.Status.CANCELADO)

    def test_ninguem_cancela_ingresso_alheio(self):
        ingresso = Ingresso.objects.create(
            usuario=self.usuario, evento=self.evento, valor=Decimal("100.00")
        )
        intruso = User.objects.create_user("intruso@teste.com", password="senha-forte-123")
        self.client.force_login(intruso)
        resposta = self.client.post(reverse("cancelar_ingresso", args=[ingresso.codigo]))
        self.assertEqual(resposta.status_code, 404)
        ingresso.refresh_from_db()
        self.assertEqual(ingresso.status, Ingresso.Status.CONFIRMADO)

    def test_cancelamento_recusa_get(self):
        ingresso = Ingresso.objects.create(
            usuario=self.usuario, evento=self.evento, valor=Decimal("100.00")
        )
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("cancelar_ingresso", args=[ingresso.codigo]))
        self.assertEqual(resposta.status_code, 405)


# =========================
# FAVORITOS
# =========================

class FavoritoTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("fa@teste.com", password="senha-forte-123")
        self.evento = criar_evento()
        self.url = reverse("alternar_favorito", args=[self.evento.slug])

    def test_alternar_salva_e_remove(self):
        self.client.force_login(self.usuario)
        self.client.post(self.url)
        self.assertEqual(Favorito.objects.count(), 1)
        self.client.post(self.url)
        self.assertEqual(Favorito.objects.count(), 0)

    def test_favoritar_nao_redireciona_para_fora_do_site(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, {"proximo": "https://exemplo-malicioso.test/"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, self.evento.get_absolute_url())

    def test_favoritar_respeita_destino_interno(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, {"proximo": reverse("lista_eventos")})
        self.assertRedirects(resposta, reverse("lista_eventos"))

    def test_favoritar_exige_login(self):
        resposta = self.client.post(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Favorito.objects.count(), 0)


# =========================
# EVENTOS DO USUÁRIO
# =========================

class CadastroDeEventoTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("org@teste.com", password="senha-forte-123")
        self.client.force_login(self.usuario)

    def dados(self, **extras):
        inicio = timezone.localtime() + timedelta(days=20)
        return {
            "nome": "Festival Novo de Teste",
            "descricao": "Uma descrição suficiente para o formulário.",
            "data": inicio.strftime("%Y-%m-%dT%H:%M"),
            "data_fim": "",
            "modalidade": "presencial",
            "local": "Espaço Cultural",
            "endereco": "SDC Lote 5",
            "regiao": Regiao.ASA_NORTE,
            "cidade": "Brasília",
            "categoria": Categoria.FESTIVAIS,
            "preco": "75.00",
            "organizador": "Produtora Teste",
            **extras,
        }

    def test_evento_criado_fica_pendente(self):
        self.client.post(reverse("criar_evento"), self.dados())
        evento = Evento.objects.get(nome="Festival Novo de Teste")
        self.assertEqual(evento.status, Evento.Status.PENDENTE)
        self.assertEqual(evento.criado_por, self.usuario)

    def test_data_no_passado_e_recusada(self):
        passado = (timezone.localtime() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        resposta = self.client.post(reverse("criar_evento"), self.dados(data=passado))
        self.assertFormError(resposta.context["form"], "data", "A data de início precisa ser no futuro.")

    def test_termino_antes_do_inicio_e_recusado(self):
        inicio = timezone.localtime() + timedelta(days=20)
        resposta = self.client.post(
            reverse("criar_evento"),
            self.dados(data_fim=(inicio - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")),
        )
        self.assertFormError(resposta.context["form"], "data_fim", "O término precisa ser depois do início.")

    def test_preco_obrigatorio_quando_nao_e_gratuito(self):
        resposta = self.client.post(reverse("criar_evento"), self.dados(preco=""))
        self.assertFormError(
            resposta.context["form"], "preco", "Informe o preço ou marque o evento como gratuito."
        )

    def test_nao_edita_evento_de_outra_pessoa(self):
        alheio = criar_evento(criado_por=User.objects.create_user("z@teste.com"))
        resposta = self.client.get(reverse("editar_evento", args=[alheio.slug]))
        self.assertEqual(resposta.status_code, 404)

    def test_editar_rejeitado_devolve_para_a_fila(self):
        meu = criar_evento(criado_por=self.usuario, status=Evento.Status.REJEITADO)
        self.client.post(reverse("editar_evento", args=[meu.slug]), self.dados(nome=meu.nome))
        meu.refresh_from_db()
        self.assertEqual(meu.status, Evento.Status.PENDENTE)


# =========================
# CONTA
# =========================

class ContaTests(TestCase):
    def test_cadastro_cria_usuario_e_autentica(self):
        resposta = self.client.post(reverse("cadastro"), {
            "full_name": "Maria Silva",
            "email": "Maria@Teste.com",
            "password1": "brasilia-2026-df",
            "password2": "brasilia-2026-df",
            "terms": "on",
        })
        self.assertRedirects(resposta, reverse("home"))
        usuario = User.objects.get(email="maria@teste.com")
        self.assertEqual(usuario.first_name, "Maria")
        self.assertIn("_auth_user_id", self.client.session)

    def test_email_duplicado_e_recusado(self):
        User.objects.create_user("ja@existe.com", email="ja@existe.com", password="x")
        resposta = self.client.post(reverse("cadastro"), {
            "full_name": "Outra Pessoa",
            "email": "ja@existe.com",
            "password1": "brasilia-2026-df",
            "password2": "brasilia-2026-df",
            "terms": "on",
        })
        self.assertFormError(resposta.context["form"], "email", "Já existe uma conta com este e-mail.")

    def test_senhas_diferentes_sao_recusadas(self):
        resposta = self.client.post(reverse("cadastro"), {
            "full_name": "Maria Silva",
            "email": "nova@teste.com",
            "password1": "brasilia-2026-df",
            "password2": "outra-coisa-2026",
            "terms": "on",
        })
        self.assertFormError(resposta.context["form"], "password2", "As senhas não coincidem.")

    def test_logout_por_get_nao_e_permitido(self):
        User.objects.create_user("a@b.com", password="senha-forte-123")
        self.client.login(username="a@b.com", password="senha-forte-123")
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)

    def test_logout_por_post_encerra_a_sessao(self):
        User.objects.create_user("a@b.com", password="senha-forte-123")
        self.client.login(username="a@b.com", password="senha-forte-123")
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_recuperacao_de_senha_completa_o_fluxo(self):
        resposta = self.client.post(reverse("password_reset"), {"email": "ninguem@teste.com"})
        self.assertRedirects(resposta, reverse("password_reset_done"))
        self.assertEqual(self.client.get(reverse("password_reset_done")).status_code, 200)


# =========================
# PÁGINAS E SEO
# =========================

class PaginasTests(TestCase):
    def test_paginas_publicas_respondem(self):
        for nome in ["home", "lista_eventos", "ajuda", "sobre", "termos", "privacidade"]:
            with self.subTest(pagina=nome):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_areas_privadas_exigem_login(self):
        for nome in ["meus_ingressos", "meus_eventos", "meus_favoritos", "criar_evento"]:
            with self.subTest(pagina=nome):
                resposta = self.client.get(reverse(nome))
                self.assertEqual(resposta.status_code, 302)
                self.assertIn(reverse("login"), resposta.url)

    def test_sitemap_lista_os_eventos(self):
        evento = criar_evento()
        resposta = self.client.get("/sitemap.xml")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, evento.slug)

    def test_robots_aponta_para_o_sitemap(self):
        resposta = self.client.get(reverse("robots_txt"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Sitemap:")
        self.assertContains(resposta, "Disallow: /admin/")

    def test_pagina_inexistente_devolve_404(self):
        self.assertEqual(self.client.get("/evento/nao-existe/").status_code, 404)


# =========================
# IMPORTAÇÃO
# =========================

class ImportacaoTests(TestCase):
    def importado(self, **extras):
        from ..ingestao import EventoImportado

        padrao = {
            "id_externo": "12345",
            "nome": "Evento Importado",
            "data": timezone.now() + timedelta(days=10),
            "local": "Arena de Taguatinga",
            "link_original": "https://exemplo.test/evento/12345",
        }
        return EventoImportado(**{**padrao, **extras})

    def test_importacao_e_idempotente(self):
        from ..ingestao import salvar_importados

        salvar_importados([self.importado()], fonte="teste")
        resultado = salvar_importados([self.importado(nome="Nome Atualizado")], fonte="teste")

        self.assertEqual(Evento.objects.count(), 1)
        self.assertEqual(resultado["atualizados"], 1)
        self.assertEqual(Evento.objects.get().nome, "Nome Atualizado")

    def test_evento_sem_data_e_descartado(self):
        from ..ingestao import salvar_importados

        resultado = salvar_importados([self.importado(data=None)], fonte="teste")
        self.assertEqual(resultado["ignorados"], 1)
        self.assertEqual(Evento.objects.count(), 0)

    def test_regiao_inferida_pelo_local(self):
        from ..ingestao import salvar_importados

        salvar_importados([self.importado()], fonte="teste")
        self.assertEqual(Evento.objects.get().regiao, Regiao.TAGUATINGA)

    def test_correcao_manual_de_regiao_sobrevive_a_reimportacao(self):
        from ..ingestao import salvar_importados

        salvar_importados([self.importado()], fonte="teste")
        evento = Evento.objects.get()
        evento.regiao = Regiao.SAMAMBAIA
        evento.destaque = True
        evento.save()

        salvar_importados([self.importado(nome="Nome novo")], fonte="teste")
        evento.refresh_from_db()

        self.assertEqual(evento.regiao, Regiao.SAMAMBAIA)
        self.assertTrue(evento.destaque)
        self.assertEqual(evento.nome, "Nome novo")

    def test_regiao_vazia_e_preenchida_na_reimportacao(self):
        from ..ingestao import salvar_importados

        salvar_importados([self.importado(local="Local sem região")], fonte="teste")
        self.assertEqual(Evento.objects.get().regiao, "")

        salvar_importados([self.importado()], fonte="teste")
        self.assertEqual(Evento.objects.get().regiao, Regiao.TAGUATINGA)

    def test_importacao_nao_apaga_eventos_existentes(self):
        criar_evento(nome="Evento manual")
        from ..ingestao import salvar_importados

        salvar_importados([self.importado()], fonte="teste")
        self.assertTrue(Evento.objects.filter(nome="Evento manual").exists())

    def test_modulo_antigo_continua_importavel(self):
        """eventos.scraping virou eventos.ingestao, mas o import antigo não pode
        quebrar de uma vez — script de deploy e código de terceiros dependem dele."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from ..scraping import EventoImportado, salvar_importados

        self.assertIsNotNone(EventoImportado)
        self.assertIsNotNone(salvar_importados)
