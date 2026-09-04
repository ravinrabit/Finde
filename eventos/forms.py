from datetime import datetime, time

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from .constants import ACESSOS, ORDENACOES, PERIODOS, PRECOS, RAIOS, Categoria, Regiao
from .models import Evento, Produtor
from .services.lgpd import VERSAO_PRIVACIDADE, VERSAO_TERMOS

TAMANHO_MAXIMO_IMAGEM = 5 * 1024 * 1024
FORMATOS_IMAGEM = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class AcessibilidadeMixin:
    """Liga cada input à sua ajuda e ao seu erro por aria-describedby.

    Isso precisa acontecer depois da validação, quando já se sabe quais campos
    falharam — por isso é um mixin de formulário, e não um atributo do widget.
    O template partials/campo.html renderiza os ids correspondentes.
    """

    def acessibilizar(self):
        for nome, campo in self.fields.items():
            atributos = campo.widget.attrs
            auto_id = self.add_prefix(nome)
            descritores = []
            if campo.help_text:
                descritores.append(f"ajuda-id_{auto_id}")
            if self.is_bound and self.errors.get(nome):
                descritores.append(f"erro-id_{auto_id}")
                atributos["aria-invalid"] = "true"
            if descritores:
                atributos["aria-describedby"] = " ".join(descritores)
            if campo.required:
                atributos.setdefault("aria-required", "true")


# =========================
# CONTA
# =========================

class LoginForm(AuthenticationForm):
    # Aceita e-mail (o caso de todo mundo que se cadastrou pelo site) e também
    # username simples, senão um superusuário criado por createsuperuser não
    # consegue entrar pela página de login.
    username = forms.CharField(
        label="E-mail",
        max_length=150,
        widget=forms.TextInput(
            attrs={"autocomplete": "username", "placeholder": "voce@email.com", "inputmode": "email"}
        ),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "placeholder": "Sua senha"}
        ),
    )
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail ou senha incorretos.",
        "inactive": "Esta conta está desativada.",
    }

    def clean_username(self):
        return self.cleaned_data["username"].lower().strip()


class CadastroForm(AcessibilidadeMixin, forms.Form):
    full_name = forms.CharField(
        label="Nome completo",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Seu nome completo"}),
        error_messages={"required": "Informe seu nome completo."},
    )
    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "voce@email.com"}),
        error_messages={
            "required": "Informe um e-mail.",
            "invalid": "Digite um e-mail válido.",
        },
    )
    password1 = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": "Mínimo de 8 caracteres"}
        ),
        help_text="Use pelo menos 8 caracteres, com letras e números.",
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": "Digite a senha novamente"}
        ),
    )
    terms = forms.BooleanField(
        label="Li e aceito os Termos de Uso e a Política de Privacidade",
        error_messages={"required": "Aceite os Termos de Uso para continuar."},
    )

    def clean_full_name(self):
        nome = " ".join(self.cleaned_data["full_name"].split())
        if len(nome) < 3:
            raise forms.ValidationError("Informe seu nome completo.")
        return nome

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        # O e-mail também vira username, cujo campo tem 150 caracteres.
        if len(email) > 150:
            raise forms.ValidationError("Este e-mail é longo demais para criar uma conta.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean_password1(self):
        senha = self.cleaned_data["password1"]
        validate_password(senha)
        return senha

    def clean(self):
        dados = super().clean()
        senha, confirmacao = dados.get("password1"), dados.get("password2")
        if senha and confirmacao and senha != confirmacao:
            self.add_error("password2", "As senhas não coincidem.")
        self.acessibilizar()
        return dados

    def criar_usuario(self, ip=None):
        """Cria o usuário e registra o consentimento.

        A checagem de e-mail duplicado no clean deixa uma janela entre o
        .exists() e o create: dois cadastros simultâneos passavam os dois e o
        segundo estourava IntegrityError, ou seja, erro 500 no lugar de
        mensagem. O try aqui fecha essa janela.
        """
        from .models import AceiteDeTermos

        nome = self.cleaned_data["full_name"]
        primeiro, _, sobrenome = nome.partition(" ")
        try:
            with transaction.atomic():
                usuario = User.objects.create_user(
                    username=self.cleaned_data["email"],
                    email=self.cleaned_data["email"],
                    password=self.cleaned_data["password1"],
                    first_name=primeiro,
                    last_name=sobrenome,
                )
                AceiteDeTermos.objects.create(
                    usuario=usuario,
                    versao_termos=VERSAO_TERMOS,
                    versao_privacidade=VERSAO_PRIVACIDADE,
                    ip=ip,
                )
        except IntegrityError:
            self.add_error("email", "Já existe uma conta com este e-mail.")
            return None
        return usuario


class ExclusaoDeContaForm(AcessibilidadeMixin, forms.Form):
    """Exclusão de conta é irreversível: exige senha e confirmação escrita."""

    senha = forms.CharField(
        label="Sua senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    confirmacao = forms.CharField(
        label='Digite EXCLUIR para confirmar',
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "EXCLUIR"}),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean_senha(self):
        senha = self.cleaned_data["senha"]
        if self.usuario and not self.usuario.check_password(senha):
            raise forms.ValidationError("Senha incorreta.")
        return senha

    def clean_confirmacao(self):
        texto = self.cleaned_data["confirmacao"].strip().upper()
        if texto != "EXCLUIR":
            raise forms.ValidationError("Digite exatamente EXCLUIR para confirmar.")
        return texto

    def clean(self):
        dados = super().clean()
        self.acessibilizar()
        return dados


# =========================
# PRODUTOR
# =========================

class ProdutorForm(AcessibilidadeMixin, forms.ModelForm):
    class Meta:
        model = Produtor
        fields = ["nome", "bio", "logo", "email", "site", "instagram", "whatsapp"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Nome que aparece nos eventos"}),
            "bio": forms.Textarea(attrs={"rows": 5, "placeholder": "Quem é, o que produz…"}),
            "instagram": forms.TextInput(attrs={"placeholder": "@seuperfil"}),
            "whatsapp": forms.TextInput(attrs={"placeholder": "(61) 90000-0000"}),
            "site": forms.URLInput(attrs={"placeholder": "https://…"}),
            "logo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        labels = {"bio": "Descrição", "logo": "Logo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if not isinstance(campo.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                campo.widget.attrs.setdefault("class", "campo")

    def clean_logo(self):
        return validar_imagem(self.cleaned_data.get("logo"))

    def clean(self):
        dados = super().clean()
        self.acessibilizar()
        return dados


class ColarLinkForm(forms.Form):
    """Fonte de eventos nº 3: o produtor cola o link do próprio evento.

    Legítimo porque é o dono pedindo. Resolve o maior atrito do cadastro, que é
    redigitar tudo o que já está publicado em outro lugar.
    """

    url = forms.URLField(
        label="Link do evento",
        widget=forms.URLInput(
            attrs={
                "placeholder": "https://… (Sympla, site do espaço, sua página)",
                "class": "campo",
                "autocomplete": "url",
            }
        ),
        help_text="Vamos ler o que estiver publicado e preencher o formulário. Você confere antes de enviar.",
    )


# =========================
# CADASTRO DE EVENTO
# =========================

def validar_imagem(imagem):
    if not imagem or not hasattr(imagem, "content_type"):
        return imagem
    if imagem.size > TAMANHO_MAXIMO_IMAGEM:
        raise forms.ValidationError("A imagem precisa ter no máximo 5 MB.")
    if imagem.content_type not in FORMATOS_IMAGEM:
        raise forms.ValidationError("Envie uma imagem JPG, PNG, WEBP ou GIF.")
    return imagem


class EventoForm(AcessibilidadeMixin, forms.ModelForm):
    class Meta:
        model = Evento
        fields = [
            "nome", "imagem", "resumo", "descricao",
            "data", "data_fim",
            "modalidade", "local", "endereco", "regiao", "cidade",
            "categoria", "gratuito", "preco",
            "capacidade", "limite_por_usuario",
            "organizador", "link_ingressos",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Festival de Jazz do Cerrado"}),
            "resumo": forms.TextInput(
                attrs={"placeholder": "Uma frase que resume o evento", "maxlength": 200}
            ),
            "descricao": forms.Textarea(
                attrs={"rows": 8, "placeholder": "Conte o que vai acontecer, quem se apresenta, o que levar…"}
            ),
            "data": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "data_fim": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "local": forms.TextInput(attrs={"placeholder": "Ex.: Clube do Choro", "list": "locais-conhecidos"}),
            "endereco": forms.TextInput(attrs={"placeholder": "Ex.: SDC Eixo Monumental, Lote 5"}),
            "preco": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0,00"}),
            "capacidade": forms.NumberInput(attrs={"min": "1", "placeholder": "Deixe vazio se não há limite"}),
            "limite_por_usuario": forms.NumberInput(attrs={"min": "1", "max": "10"}),
            "organizador": forms.TextInput(attrs={"placeholder": "Quem realiza o evento"}),
            "link_ingressos": forms.URLInput(attrs={"placeholder": "https://…"}),
            "imagem": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        labels = {
            "nome": "Nome do evento",
            "imagem": "Imagem de capa",
            "resumo": "Resumo",
            "descricao": "Descrição",
            "modalidade": "Formato",
            "local": "Nome do local",
            "regiao": "Região",
            "categoria": "Categoria",
            "gratuito": "Este evento é gratuito",
            "preco": "Preço a partir de (R$)",
            "capacidade": "Capacidade (lugares)",
            "limite_por_usuario": "Máximo de ingressos por pessoa",
            "organizador": "Organizador",
            "link_ingressos": "Link externo de ingressos (opcional)",
        }
        help_texts = {
            "resumo": "Aparece nos cards de listagem.",
            "capacidade": "Quando o total de reservas atinge esse número, o evento aparece como esgotado.",
            "link_ingressos": "Se a venda acontece em outra plataforma, informe o endereço aqui.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].required = True
        self.fields["regiao"].required = True
        self.fields["descricao"].required = True
        self.fields["categoria"].choices = [("", "Selecione uma categoria")] + list(
            Categoria.choices
        )
        self.fields["regiao"].choices = [("", "Selecione uma região")] + list(Regiao.choices)
        for campo in self.fields.values():
            if isinstance(campo.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                continue
            campo.widget.attrs.setdefault("class", "campo")

    def clean_imagem(self):
        return validar_imagem(self.cleaned_data.get("imagem"))

    def clean_data(self):
        """Data no futuro é exigência de evento novo, não de evento existente.

        A regra valia também na edição: quem digitou a data errada e deixou
        passar ficava com o formulário permanentemente inválido, sem conseguir
        nem corrigir a descrição de um evento que já aconteceu.
        """
        data = self.cleaned_data["data"]
        e_novo = self.instance.pk is None
        # O widget tem precisão de minuto; o valor no banco pode ter segundos.
        # Sem truncar, reenviar a MESMA data seria lido como alteração, e o
        # evento passado continuaria impossível de corrigir.
        mudou = not e_novo and Evento._comparavel(data) != Evento._comparavel(self.instance.data)
        if (e_novo or mudou) and data < timezone.now():
            raise forms.ValidationError("A data de início precisa ser no futuro.")
        return data

    def clean_limite_por_usuario(self):
        """Campo com default não pode ser obrigatório no formulário.

        Ele foi acrescentado nesta evolução e, sendo `blank=False`, passou a ser
        exigido de todo mundo — quebrando quem já enviava o formulário sem ele.
        Em branco significa "use o padrão".
        """
        valor = self.cleaned_data.get("limite_por_usuario")
        if valor in (None, ""):
            return Evento._meta.get_field("limite_por_usuario").get_default()
        return valor

    def clean_capacidade(self):
        capacidade = self.cleaned_data.get("capacidade")
        if capacidade is None:
            return capacidade
        if capacidade < 1:
            raise forms.ValidationError("A capacidade precisa ser pelo menos 1.")
        if self.instance.pk:
            ja_reservados = self.instance.ingressos_confirmados
            if capacidade < ja_reservados:
                raise forms.ValidationError(
                    f"Já existem {ja_reservados} ingresso(s) reservado(s). "
                    "A capacidade não pode ser menor que isso."
                )
        return capacidade

    def clean(self):
        dados = super().clean()
        inicio, fim = dados.get("data"), dados.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim", "O término precisa ser depois do início.")

        if dados.get("modalidade") == "online":
            dados["regiao"] = Regiao.ONLINE
            if "regiao" in self.errors:
                del self.errors["regiao"]

        if not dados.get("gratuito") and dados.get("preco") is None:
            self.add_error("preco", "Informe o preço ou marque o evento como gratuito.")
        self.acessibilizar()
        return dados


# =========================
# BUSCA E FILTROS
# =========================

class FiltroEventosForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Buscar",
        widget=forms.TextInput(
            attrs={"placeholder": "Evento, artista ou local", "type": "search"}
        ),
    )
    categoria = forms.ChoiceField(required=False, label="Categoria", choices=[])
    regiao = forms.ChoiceField(required=False, label="Região", choices=[])
    periodo = forms.ChoiceField(required=False, label="Quando", choices=[])
    de = forms.DateField(
        required=False, label="De",
        widget=forms.DateInput(attrs={"type": "date"}), input_formats=["%Y-%m-%d"],
    )
    ate = forms.DateField(
        required=False, label="Até",
        widget=forms.DateInput(attrs={"type": "date"}), input_formats=["%Y-%m-%d"],
    )
    preco = forms.ChoiceField(required=False, label="Preço", choices=[])
    raio = forms.ChoiceField(required=False, label="Distância", choices=[])
    acesso = forms.MultipleChoiceField(
        required=False, label="Acessibilidade e transporte",
        choices=ACESSOS, widget=forms.CheckboxSelectMultiple,
    )
    lat = forms.FloatField(required=False, widget=forms.HiddenInput)
    lon = forms.FloatField(required=False, widget=forms.HiddenInput)
    ordenar = forms.ChoiceField(required=False, label="Ordenar por", choices=ORDENACOES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].choices = [("", "Todas as categorias")] + list(Categoria.choices)
        self.fields["regiao"].choices = [("", "Todo o DF")] + list(Regiao.choices)
        self.fields["periodo"].choices = [("", "Qualquer data")] + PERIODOS
        self.fields["preco"].choices = [("", "Qualquer preço")] + PRECOS
        self.fields["raio"].choices = [("", "Qualquer distância")] + RAIOS
        for nome, campo in self.fields.items():
            if nome in ("acesso", "lat", "lon"):
                continue
            campo.widget.attrs.setdefault("class", "campo")

    def valor(self, nome):
        """Filtro inválido na querystring é tratado como ausente, nunca como erro.

        A checagem é por campo: is_valid() é falso quando *qualquer* campo falha, e
        ler o resultado dele descartaria também os filtros que estavam corretos.
        cleaned_data só contém os campos que passaram, que é exatamente o que queremos.
        """
        if not self.is_bound:
            return "" if nome not in ("acesso",) else []
        self.is_valid()
        vazio = [] if nome == "acesso" else ""
        return self.cleaned_data.get(nome) or vazio

    def coordenadas(self):
        """Só usa lat/lon quando os dois vêm e estão dentro de um intervalo plausível."""
        lat, lon = self.valor("lat"), self.valor("lon")
        if lat in ("", None) or lon in ("", None):
            return None
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return lat, lon

    def intervalo(self):
        """(início, fim) em datetime aware, a partir dos campos de data."""
        de, ate = self.valor("de"), self.valor("ate")
        if not de and not ate:
            return None
        fuso = timezone.get_current_timezone()
        inicio = (
            timezone.make_aware(datetime.combine(de, time.min), fuso) if de else timezone.now()
        )
        fim = (
            timezone.make_aware(datetime.combine(ate, time.max), fuso)
            if ate
            else inicio + timezone.timedelta(days=365)
        )
        if fim < inicio:
            inicio, fim = fim, inicio
        return inicio, fim

    @property
    def filtros_ativos(self):
        rotulos = {"q": "Busca", "de": "A partir de", "ate": "Até"}
        ativos = []
        for nome in ("q", "categoria", "regiao", "periodo", "de", "ate", "preco", "raio"):
            valor = self.valor(nome)
            if not valor:
                continue
            campo = self.fields[nome]
            if hasattr(campo, "choices"):
                texto = dict(campo.choices).get(valor, valor)
            elif nome in ("de", "ate"):
                texto = f"{rotulos[nome]} {valor:%d/%m/%Y}"
            else:
                texto = f'"{valor}"'
            ativos.append(
                {
                    "nome": nome,
                    "valor": valor if nome not in ("de", "ate") else valor.isoformat(),
                    "rotulo": texto,
                    "campo": rotulos.get(nome, campo.label),
                }
            )
        for acesso in self.valor("acesso"):
            ativos.append(
                {
                    "nome": "acesso",
                    "valor": acesso,
                    "rotulo": dict(ACESSOS).get(acesso, acesso),
                    "campo": "Acessibilidade",
                }
            )
        return ativos
