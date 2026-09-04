{% load static %}/*
 * Service worker do Finde.
 *
 * Objetivo é modesto de propósito: deixar o app instalável (critério de
 * "installability" do Chrome/Android exige um service worker com fetch
 * handler) e não quebrar numa queda de conexão no meio da navegação — não
 * é um app offline-first. A agenda de eventos muda o tempo todo, então
 * páginas de navegação sempre tentam a rede primeiro; só caem para o cache
 * (ou para /offline/) quando a rede falha de verdade.
 *
 * VERSAO precisa mudar a cada alteração deste arquivo para os caches
 * antigos serem descartados no "activate". Os arquivos estáticos em si já
 * têm hash no nome em produção (WhiteNoise), então não precisam de
 * versionamento manual — só o "app shell" listado abaixo.
 */
const VERSAO = "finde-v1";
const CACHE_ESTATICO = `${VERSAO}-estatico`;
const CACHE_RUNTIME = `${VERSAO}-runtime`;
const URL_OFFLINE = "{% url 'pagina_offline' %}";
const PREFIXO_ESTATICO = "{% static '' %}";

const APP_SHELL = [
    "{% static 'css/finde.css' %}",
    "{% static 'js/finde.js' %}",
    "{% static 'img/logo-finde.png' %}",
    "{% static 'img/favicon-32.png' %}",
    "{% static 'img/icone-192.png' %}",
    URL_OFFLINE,
];

self.addEventListener("install", (evento) => {
    evento.waitUntil(
        caches.open(CACHE_ESTATICO)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (evento) => {
    evento.waitUntil(
        caches.keys()
            .then((chaves) => Promise.all(
                chaves
                    .filter((chave) => chave.startsWith("finde-") && !chave.startsWith(VERSAO))
                    .map((chave) => caches.delete(chave))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (evento) => {
    const requisicao = evento.request;

    // Só GET, só mesma origem — o resto (POST de formulários, fontes do
    // Google, chamadas de terceiros) segue direto pela rede sem passar
    // pelo cache.
    if (requisicao.method !== "GET" || new URL(requisicao.url).origin !== self.location.origin) {
        return;
    }

    // Navegação (o usuário abrindo uma página): rede primeiro, porque a
    // agenda muda o tempo todo. Só usa o cache se a rede falhar mesmo.
    if (requisicao.mode === "navigate") {
        evento.respondWith(
            fetch(requisicao).catch(() =>
                caches.match(requisicao).then((resposta) => resposta || caches.match(URL_OFFLINE))
            )
        );
        return;
    }

    // Estático (CSS/JS/imagens em /static/): cache primeiro. Em produção o
    // nome do arquivo já muda a cada deploy (hash do WhiteNoise), então
    // servir do cache não corre o risco de prender uma versão velha.
    if (new URL(requisicao.url).pathname.startsWith(PREFIXO_ESTATICO)) {
        evento.respondWith(
            caches.match(requisicao).then((resposta) => {
                if (resposta) return resposta;
                return fetch(requisicao).then((resposta_rede) => {
                    const copia = resposta_rede.clone();
                    caches.open(CACHE_RUNTIME).then((cache) => cache.put(requisicao, copia));
                    return resposta_rede;
                });
            })
        );
    }
});
