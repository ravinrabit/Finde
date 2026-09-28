from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class RequirementsProdTests(SimpleTestCase):
    """requirements-prod.txt já teve uma linha "." solta (sobra de uma
    limpeza de comentários) que fazia o pip tentar instalar o diretório
    atual como pacote e falhar com "not installable" — quebrando todo
    deploy que rodasse "pip install -r requirements-prod.txt" num
    checkout limpo. Este teste garante que cada linha do arquivo é um
    include (-r) ou um requisito com nome de pacote, nunca um caminho
    solto.
    """

    def test_todas_as_linhas_sao_include_ou_requisito_nomeado(self):
        conteudo = (BASE_DIR / "requirements-prod.txt").read_text()
        for linha in conteudo.splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            if linha.startswith("-r "):
                continue
            self.assertRegex(
                linha,
                r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,_-]+\])?",
                f"Linha inválida em requirements-prod.txt: {linha!r}",
            )
