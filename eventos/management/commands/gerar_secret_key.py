import secrets

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Gera uma SECRET_KEY nova e explica o que fazer com a antiga."

    def add_arguments(self, parser):
        parser.add_argument("--so-a-chave", action="store_true", help="Imprime só a chave.")

    def handle(self, *args, **opcoes):
        chave = secrets.token_urlsafe(50)
        if opcoes["so_a_chave"]:
            self.stdout.write(chave)
            return

        self.stdout.write(self.style.SUCCESS("SECRET_KEY=" + chave))
        self.stdout.write(
            "\n"
            "Cole no .env e reinicie a aplicação.\n"
            "\n"
            "A chave antiga esteve versionada no Git e deve ser tratada como comprometida:\n"
            "com ela, qualquer pessoa forja cookie de sessão e token de recuperação de senha.\n"
            "\n"
            "  1. Troque a chave (linha acima).\n"
            "  2. Invalide as sessões existentes:\n"
            "       python manage.py clearsessions\n"
            "       # ou, para derrubar todo mundo agora:\n"
            "       python manage.py shell -c \"from django.contrib.sessions.models import \"\n"
            "       \"Session; Session.objects.all().delete()\"\n"
            "  3. Limpe o histórico do Git (a chave continua lá até isso ser feito):\n"
            "       pip install git-filter-repo\n"
            "       git filter-repo --path .env --invert-paths --force\n"
            "       git push --force --all      # combine com quem clonou o repositório\n"
            "     Se o repositório for público ou já tiver sido clonado por terceiros,\n"
            "     considere-o queimado e recrie-o.\n"
            "  4. Rotacione também o que estava no mesmo .env: senha de SMTP, credencial de\n"
            "     banco, token de storage e qualquer chave de API.\n"
        )
