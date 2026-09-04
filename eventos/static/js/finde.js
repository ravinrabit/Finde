(function () {
    "use strict";

    const $ = (seletor, raiz) => (raiz || document).querySelector(seletor);
    const $$ = (seletor, raiz) => Array.from((raiz || document).querySelectorAll(seletor));

    function csrf() {
        const campo = $('input[name="csrfmiddlewaretoken"]');
        return campo ? campo.value : "";
    }


    /* =========================
       MENU MOBILE
       ========================= */

    function iniciarGaveta() {
        const gatilho = $("[data-menu-gatilho]");
        const gaveta = $("[data-gaveta]");
        if (!gatilho || !gaveta) return;

        let focoAnterior = null;
        let posicaoRolagem = 0;

        // `overflow: hidden` no body não trava a rolagem no Safari/iOS: o fundo
        // ainda "arrasta" (rubber-banding) atrás da gaveta. Fixar o body na
        // posição atual é a técnica que realmente bloqueia o scroll em iOS,
        // preservando o ponto de rolagem ao fechar.
        const travarRolagem = () => {
            posicaoRolagem = window.scrollY || window.pageYOffset || 0;
            document.body.style.position = "fixed";
            document.body.style.top = `-${posicaoRolagem}px`;
            document.body.style.left = "0";
            document.body.style.right = "0";
            document.body.style.width = "100%";
        };

        const destravarRolagem = () => {
            document.body.style.position = "";
            document.body.style.top = "";
            document.body.style.left = "";
            document.body.style.right = "";
            document.body.style.width = "";
            window.scrollTo(0, posicaoRolagem);
        };

        const abrir = () => {
            focoAnterior = document.activeElement;
            gaveta.dataset.aberta = "";
            gatilho.setAttribute("aria-expanded", "true");
            travarRolagem();
            const primeiro = $("a, button", gaveta);
            if (primeiro) primeiro.focus();
        };

        const fechar = () => {
            delete gaveta.dataset.aberta;
            gatilho.setAttribute("aria-expanded", "false");
            destravarRolagem();
            if (focoAnterior) focoAnterior.focus();
        };

        gatilho.addEventListener("click", abrir);
        $$("[data-gaveta-fechar]", gaveta).forEach((el) => el.addEventListener("click", fechar));

        document.addEventListener("keydown", (evento) => {
            if (evento.key !== "Escape" || !("aberta" in gaveta.dataset)) return;
            fechar();
        });

        gaveta.addEventListener("keydown", (evento) => {
            if (evento.key !== "Tab") return;
            const focaveis = $$("a[href], button:not([disabled])", gaveta);
            if (!focaveis.length) return;
            const primeiro = focaveis[0];
            const ultimo = focaveis[focaveis.length - 1];
            if (evento.shiftKey && document.activeElement === primeiro) {
                evento.preventDefault();
                ultimo.focus();
            } else if (!evento.shiftKey && document.activeElement === ultimo) {
                evento.preventDefault();
                primeiro.focus();
            }
        });
    }


    /* =========================
       FILTROS
       ========================= */

    function iniciarFiltros() {
        const gatilho = $("[data-filtros-gatilho]");
        const corpo = $("[data-filtros-corpo]");
        if (gatilho && corpo) {
            gatilho.addEventListener("click", () => {
                const aberto = "aberto" in corpo.dataset;
                if (aberto) delete corpo.dataset.aberto;
                else corpo.dataset.aberto = "";
                gatilho.setAttribute("aria-expanded", String(!aberto));
            });
        }

        // A página tem DOIS formulários com [data-filtros-form]: o painel de
        // filtros e o seletor "Ordenar por". querySelector devolvia só o
        // primeiro, então mudar a ordenação não enviava nada. $$ pega os dois.
        $$("[data-filtros-form]").forEach((formulario) => {
            $$("select", formulario).forEach((campo) => {
                campo.addEventListener("change", () => formulario.requestSubmit());
            });
            $$("input[type='date']", formulario).forEach((campo) => {
                campo.addEventListener("change", () => formulario.requestSubmit());
            });
        });
    }


    /* =========================
       PERTO DE MIM
       ========================= */

    function iniciarLocalizacao() {
        $$("[data-perto-de-mim]").forEach((botao) => {
            if (!navigator.geolocation) {
                botao.hidden = true;
                return;
            }
            botao.addEventListener("click", () => {
                const rotulo = botao.querySelector("[data-rotulo]") || botao;
                const original = rotulo.textContent;
                rotulo.textContent = "Localizando…";
                botao.disabled = true;

                navigator.geolocation.getCurrentPosition(
                    (posicao) => {
                        const url = new URL(window.location.href);
                        url.searchParams.set("lat", posicao.coords.latitude.toFixed(5));
                        url.searchParams.set("lon", posicao.coords.longitude.toFixed(5));
                        if (!url.searchParams.get("raio")) {
                            url.searchParams.set("raio", botao.dataset.raio || "5");
                        }
                        url.searchParams.set("ordenar", "distancia");
                        url.searchParams.delete("page");
                        window.location.href = url.toString();
                    },
                    () => {
                        rotulo.textContent = original;
                        botao.disabled = false;
                        const aviso = $("[data-localizacao-erro]");
                        if (aviso) aviso.hidden = false;
                    },
                    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
                );
            });
        });
    }


    /* =========================
       SENHA
       ========================= */

    function iniciarSenha() {
        $$("[data-senha-alternar]").forEach((botao) => {
            botao.addEventListener("click", () => {
                const campo = document.getElementById(botao.dataset.senhaAlternar);
                if (!campo) return;
                const oculta = campo.type === "password";
                campo.type = oculta ? "text" : "password";
                botao.setAttribute("aria-pressed", String(oculta));
                botao.setAttribute("aria-label", oculta ? "Ocultar senha" : "Mostrar senha");
            });
        });
    }


    /* =========================
       ABAS
       ========================= */

    function iniciarAbas() {
        const lista = $("[data-abas]");
        if (!lista) return;
        const abas = $$("[role='tab']", lista);

        const ativar = (aba) => {
            abas.forEach((outra) => {
                const alvo = document.getElementById(outra.getAttribute("aria-controls"));
                const ativa = outra === aba;
                outra.setAttribute("aria-selected", String(ativa));
                outra.tabIndex = ativa ? 0 : -1;
                if (alvo) alvo.hidden = !ativa;
            });
        };

        abas.forEach((aba, indice) => {
            aba.addEventListener("click", () => ativar(aba));
            aba.addEventListener("keydown", (evento) => {
                const passo = { ArrowRight: 1, ArrowLeft: -1 }[evento.key];
                if (!passo) return;
                evento.preventDefault();
                const proxima = abas[(indice + passo + abas.length) % abas.length];
                proxima.focus();
                ativar(proxima);
            });
        });
    }


    /* =========================
       UPLOAD DE IMAGEM
       ========================= */

    function iniciarUpload() {
        const area = $("[data-upload]");
        if (!area) return;
        const entrada = $("input[type='file']", area);
        const texto = $("[data-upload-texto]", area);
        const previa = $("[data-upload-previa]", area);
        if (!entrada || !previa) return;

        const mostrar = (arquivo) => {
            if (!arquivo || !arquivo.type.startsWith("image/")) return;
            const leitor = new FileReader();
            leitor.onload = (evento) => {
                previa.src = evento.target.result;
                previa.hidden = false;
                if (texto) texto.hidden = true;
            };
            leitor.readAsDataURL(arquivo);
        };

        entrada.addEventListener("change", () => mostrar(entrada.files[0]));

        ["dragover", "dragenter"].forEach((nome) =>
            area.addEventListener(nome, (evento) => {
                evento.preventDefault();
                area.dataset.arrastando = "";
            })
        );
        ["dragleave", "dragend", "drop"].forEach((nome) =>
            area.addEventListener(nome, () => delete area.dataset.arrastando)
        );

        area.addEventListener("drop", (evento) => {
            evento.preventDefault();
            const arquivos = evento.dataTransfer.files;
            if (!arquivos.length) return;
            entrada.files = arquivos;
            mostrar(arquivos[0]);
        });
    }


    /* =========================
       RESERVA
       ========================= */

    function iniciarReserva() {
        const formulario = $("[data-reserva]");
        if (!formulario) return;
        const quantidade = $("[data-reserva-quantidade]", formulario);
        const total = $("[data-reserva-total]");
        const unitario = $("[data-reserva-unitario]");
        if (!quantidade || !total) return;

        const definido = formulario.dataset.reserva === "definido";

        const recalcular = () => {
            const escolhida = formulario.querySelector("input[name='tipo']:checked");
            const preco = escolhida ? parseFloat(escolhida.dataset.valor || "0") : 0;
            const teto = parseInt(quantidade.max, 10) || 10;
            const unidades = Math.min(teto, Math.max(1, parseInt(quantidade.value, 10) || 1));
            if (unitario) unitario.textContent = definido ? formatar(preco) : "A definir";
            total.textContent = definido ? formatar(preco * unidades) : "A definir";
        };

        const formatar = (valor) =>
            valor === 0
                ? "Gratuito"
                : valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

        formulario.addEventListener("change", recalcular);
        quantidade.addEventListener("input", recalcular);
        recalcular();
    }


    /* =========================
       FAVORITOS
       ========================= */

    function iniciarFavoritos() {
        document.addEventListener("click", async (evento) => {
            const botao = evento.target.closest("[data-favoritar]");
            if (!botao) return;
            evento.preventDefault();

            const anterior = botao.getAttribute("aria-pressed") === "true";
            botao.setAttribute("aria-pressed", String(!anterior));
            botao.disabled = true;

            try {
                const resposta = await fetch(botao.dataset.favoritar, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrf(),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                if (resposta.status === 401 || resposta.redirected) {
                    window.location.href = botao.dataset.login || "/conta/entrar/";
                    return;
                }
                const dados = await resposta.json();
                botao.setAttribute("aria-pressed", String(dados.favorito));
                botao.setAttribute(
                    "aria-label",
                    dados.favorito ? "Remover dos favoritos" : "Salvar nos favoritos"
                );
            } catch (erro) {
                botao.setAttribute("aria-pressed", String(anterior));
            } finally {
                botao.disabled = false;
            }
        });
    }


    /* =========================
       COMPARTILHAR
       ========================= */

    function iniciarCompartilhar() {
        $$("[data-compartilhar]").forEach((botao) => {
            botao.addEventListener("click", async () => {
                const dados = {
                    title: botao.dataset.titulo || document.title,
                    url: botao.dataset.compartilhar || window.location.href,
                };
                if (navigator.share) {
                    try {
                        await navigator.share(dados);
                        return;
                    } catch (erro) {
                        if (erro.name === "AbortError") return;
                    }
                }
                try {
                    await navigator.clipboard.writeText(dados.url);
                    // O botão contém um <svg> além do texto. Trocar textContent
                    // apagava o ícone, que nunca voltava. Só o rótulo muda.
                    const rotulo = botao.querySelector("[data-rotulo]");
                    if (!rotulo) return;
                    const original = rotulo.dataset.original || rotulo.textContent.trim();
                    rotulo.dataset.original = original;
                    rotulo.textContent = "Link copiado";
                    setTimeout(() => {
                        rotulo.textContent = original;
                    }, 2000);
                } catch (erro) {
                    window.prompt("Copie o link do evento:", dados.url);
                }
            });
        });
    }


    /* =========================
       MAPA (Leaflet + OpenStreetMap)
       ========================= */

    function iniciarMapa() {
        const alvo = $("[data-mapa]");
        if (!alvo) return;

        // Leaflet só é baixado em quem abre o mapa: são ~150 KB que não fazem
        // sentido no orçamento de nenhuma outra página.
        carregarLeaflet()
            .then(() => desenharMapa(alvo))
            .catch(() => {
                alvo.innerHTML =
                    '<p class="mapa-erro">Não foi possível carregar o mapa. ' +
                    '<a href="/eventos/">Ver a lista de eventos</a>.</p>';
            });
    }

    function carregarLeaflet() {
        if (window.L) return Promise.resolve();
        return new Promise((resolver, rejeitar) => {
            const estilo = document.createElement("link");
            estilo.rel = "stylesheet";
            estilo.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
            document.head.appendChild(estilo);

            const script = document.createElement("script");
            script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
            script.onload = resolver;
            script.onerror = rejeitar;
            document.head.appendChild(script);
        });
    }

    async function desenharMapa(alvo) {
        const centro = [
            parseFloat(alvo.dataset.lat || "-15.7939"),
            parseFloat(alvo.dataset.lon || "-47.8828"),
        ];
        const mapa = L.map(alvo, { scrollWheelZoom: false }).setView(centro, parseInt(alvo.dataset.zoom || "11", 10));

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(mapa);

        const fonte = alvo.dataset.mapa;
        if (!fonte) return;

        const resposta = await fetch(fonte + window.location.search, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const dados = await resposta.json();
        const marcadores = [];

        (dados.features || []).forEach((item) => {
            const [lon, lat] = item.geometry.coordinates;
            const p = item.properties;
            const marcador = L.marker([lat, lon]).addTo(mapa);
            marcador.bindPopup(
                '<a class="mapa-popup" href="' + p.url + '">' +
                '<strong>' + escapar(p.nome) + '</strong>' +
                '<span>' + escapar(p.quando) + '</span>' +
                '<span>' + escapar(p.local) + '</span>' +
                '<span>' + escapar(p.preco) + '</span>' +
                (p.aproximado ? '<em>local aproximado</em>' : '') +
                '</a>'
            );
            marcadores.push(marcador);
        });

        const contador = $("[data-mapa-total]");
        if (contador) contador.textContent = marcadores.length;

        if (marcadores.length > 1) {
            mapa.fitBounds(L.featureGroup(marcadores).getBounds().pad(0.15));
        }
    }

    function escapar(texto) {
        const div = document.createElement("div");
        div.textContent = texto || "";
        return div.innerHTML;
    }


    /* =========================
       AVISOS
       ========================= */

    function iniciarAvisos() {
        $$("[data-aviso-fechar]").forEach((botao) => {
            botao.addEventListener("click", () => botao.closest(".aviso").remove());
        });
    }


    /* =========================
       PWA — SERVICE WORKER
       ========================= */

    function iniciarServiceWorker() {
        if (!("serviceWorker" in navigator)) return;

        // Em localhost o cache do service worker só atrapalha quem está
        // desenvolvendo (CSS/JS antigo "grudado"). Registrar só fora disso.
        const local = ["localhost", "127.0.0.1"].includes(window.location.hostname);
        if (local) return;

        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js").catch(() => {
                // Falhar em registrar não pode quebrar o site — é só uma
                // melhoria progressiva.
            });
        });
    }


    /* =========================
       PWA — INSTALAR APP
       ========================= */

    function iniciarInstalacao() {
        const botoes = $$("[data-instalar-app]");
        if (!botoes.length) return;

        let evento_adiado = null;

        window.addEventListener("beforeinstallprompt", (evento) => {
            // O navegador só dispara isso quando o site já cumpre os
            // critérios de instalação (manifest + service worker + HTTPS).
            // Sem isso o botão fica escondido — não tem como forçar a
            // instalação manualmente.
            evento.preventDefault();
            evento_adiado = evento;
            botoes.forEach((botao) => { botao.hidden = false; });
        });

        botoes.forEach((botao) => {
            botao.addEventListener("click", async () => {
                if (!evento_adiado) return;
                botao.disabled = true;
                evento_adiado.prompt();
                await evento_adiado.userChoice;
                evento_adiado = null;
                botao.hidden = true;
                botao.disabled = false;
            });
        });

        window.addEventListener("appinstalled", () => {
            botoes.forEach((botao) => { botao.hidden = true; });
        });
    }


    document.addEventListener("DOMContentLoaded", () => {
        iniciarGaveta();
        iniciarFiltros();
        iniciarLocalizacao();
        iniciarSenha();
        iniciarAbas();
        iniciarUpload();
        iniciarReserva();
        iniciarFavoritos();
        iniciarCompartilhar();
        iniciarAvisos();
        iniciarMapa();
        iniciarServiceWorker();
        iniciarInstalacao();
    });
})();
