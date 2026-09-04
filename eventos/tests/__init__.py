"""Suíte de testes do Finde.

Era um único tests.py com 64 testes. Virou pacote para que cada área tenha o
próprio módulo — o arquivo estava começando a ficar difícil de navegar, e
misturar o teste de paginação com o de LGPD atrapalha quem procura.

    test_legado.py       os 64 testes originais, intactos
    test_navegacao.py    paginação, ordenação, facetas, destaques
    test_moderacao.py    política de revisão de eventos publicados
    test_reservas.py     capacidade, limite por pessoa, concorrência
    test_geo.py          coordenadas, distância, raio, mapa
    test_ingestao.py     idempotência, fuso, status PENDENTE, conectores
    test_lgpd.py         exportação, exclusão, consentimento
    test_seguranca.py    rate limiting, admin, vazamento por id
"""
