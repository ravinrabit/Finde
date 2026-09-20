import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Cria um superusuário a partir de STAFF_INICIAL_EMAIL/STAFF_INICIAL_SENHA, "
        "se ainda não existir. Idempotente — seguro deixar rodando em todo deploy, "
        "pensado pra ambientes (como o plano gratuito do Render) sem shell interativo."
    )

    def handle(self, *args, **opcoes):
        email = os.environ.get("STAFF_INICIAL_EMAIL")
        senha = os.environ.get("STAFF_INICIAL_SENHA")

        if not email or not senha:
            self.stdout.write("STAFF_INICIAL_EMAIL/STAFF_INICIAL_SENHA não configurados — nada a fazer.")
            return

        if User.objects.filter(username=email).exists():
            self.stdout.write(f"Usuário {email} já existe — nada a fazer.")
            return

        User.objects.create_superuser(username=email, email=email, password=senha)
        self.stdout.write(self.style.SUCCESS(f"Superusuário {email} criado."))
