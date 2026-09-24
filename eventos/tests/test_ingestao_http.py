import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from django.test import SimpleTestCase

from ..ingestao import http as ingestao_http


def _resposta_getaddrinfo(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


class ValidarDestinoTests(SimpleTestCase):
    def test_esquema_nao_http_e_recusado(self):
        with self.assertRaises(ingestao_http.FonteIndisponivel):
            ingestao_http.validar_destino("file:///etc/passwd")

    def test_url_sem_host_e_recusada(self):
        with self.assertRaises(ingestao_http.FonteIndisponivel):
            ingestao_http.validar_destino("http:///caminho")

    def test_host_que_resolve_para_ip_privado_e_recusado(self):
        with patch.object(ingestao_http.socket, "getaddrinfo", return_value=_resposta_getaddrinfo("10.0.0.5")):
            with self.assertRaises(ingestao_http.FonteIndisponivel):
                ingestao_http.validar_destino("http://intranet.exemplo.test/")

    def test_host_que_nao_resolve_e_recusado(self):
        with patch.object(ingestao_http.socket, "getaddrinfo", side_effect=socket.gaierror("falhou")):
            with self.assertRaises(ingestao_http.FonteIndisponivel):
                ingestao_http.validar_destino("http://nao-existe.exemplo.test/")

    def test_host_publico_passa(self):
        with patch.object(ingestao_http.socket, "getaddrinfo", return_value=_resposta_getaddrinfo("93.184.216.34")):
            ingestao_http.validar_destino("http://exemplo.test/")


class RebindingDeDnsTests(SimpleTestCase):
    """O DNS de um domínio malicioso pode responder um IP público na hora da
    checagem e um IP interno segundos depois ("DNS rebinding"). O ponto
    destes testes é provar que a conexão de verdade usa exatamente o IP que
    acabou de ser validado, nunca resolvendo o host de novo por conta
    própria — senão a checagem passaria e o pedido ainda assim iria pro
    IP interno.
    """

    def test_ip_resolvido_de_novo_na_hora_de_conectar_tambem_e_bloqueado(self):
        respostas = [
            _resposta_getaddrinfo("93.184.216.34"),  # validar_destino, no início de buscar()
            _resposta_getaddrinfo("127.0.0.1"),  # resolvido de novo bem antes de conectar
        ]
        with patch.object(ingestao_http.socket, "getaddrinfo", side_effect=respostas):
            with patch.object(ingestao_http.socket, "create_connection") as conectar:
                with self.assertRaises(ingestao_http.FonteIndisponivel):
                    ingestao_http.buscar("http://rebind.exemplo.test/pagina", checar_robots=False)
        conectar.assert_not_called()

    def test_conexao_usa_o_ip_resolvido_no_momento_de_conectar(self):
        # Dois hosts públicos diferentes: a checagem inicial vê um, a conexão
        # de verdade (que é o que importa) usa o outro — nunca um terceiro.
        respostas = [
            _resposta_getaddrinfo("93.184.216.10"),  # validar_destino
            _resposta_getaddrinfo("93.184.216.20"),  # handler, imediatamente antes de conectar
        ]
        with patch.object(ingestao_http.socket, "getaddrinfo", side_effect=respostas):
            with patch.object(ingestao_http.socket, "create_connection", side_effect=OSError("recusado")) as conectar:
                with self.assertRaises(ingestao_http.FonteIndisponivel):
                    ingestao_http.buscar("http://exemplo.test/pagina", checar_robots=False)
        enderecos_tentados = [chamada.args[0][0] for chamada in conectar.call_args_list]
        self.assertEqual(enderecos_tentados, ["93.184.216.20"])


class _ServidorDeTeste:
    """Servidor HTTP real em localhost, só pra exercitar buscar() de ponta
    a ponta (redirect, limite de tamanho, decodificação) sem depender de
    rede externa.
    """

    def __init__(self, corpo=b"<html>ok</html>", redirecionar_para=None, cabecalhos_extra=None):
        self.corpo = corpo
        self.redirecionar_para = redirecionar_para
        self.cabecalhos_extra = cabecalhos_extra or {}
        testador = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if testador.redirecionar_para:
                    self.send_response(302)
                    self.send_header("Location", testador.redirecionar_para)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                for chave, valor in testador.cabecalhos_extra.items():
                    self.send_header(chave, valor)
                self.end_headers()
                self.wfile.write(testador.corpo)

            def log_message(self, *args):
                pass

        self.servidor = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    @property
    def url(self):
        porta = self.servidor.server_address[1]
        return f"http://127.0.0.1:{porta}/"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.servidor.shutdown()
        self.servidor.server_close()


class BuscarFimAFimTests(SimpleTestCase):
    """127.0.0.1 é loopback e seria bloqueado de verdade em produção — aqui
    ele representa o "IP público" que passaria na checagem, pra testar o
    resto do fluxo (conexão, redirect, limite de tamanho) contra um servidor
    de verdade em vez de mockar cada camada do urllib.
    """

    def test_busca_segue_redirect_e_le_o_conteudo(self):
        with _ServidorDeTeste(corpo="<html>alvo</html>".encode()) as alvo:
            with _ServidorDeTeste(redirecionar_para=alvo.url) as origem:
                with patch.object(ingestao_http, "_ip_bloqueado", return_value=False):
                    texto = ingestao_http.buscar(origem.url, checar_robots=False)
        self.assertIn("alvo", texto)

    def test_resposta_maior_que_o_limite_e_recusada(self):
        grande = b"a" * (ingestao_http.TAMANHO_MAXIMO + 1)
        with _ServidorDeTeste(corpo=grande) as servidor:
            with patch.object(ingestao_http, "_ip_bloqueado", return_value=False):
                with self.assertRaises(ingestao_http.FonteIndisponivel):
                    ingestao_http.buscar(servidor.url, checar_robots=False)
