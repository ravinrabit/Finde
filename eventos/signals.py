from django.contrib.auth.models import User
from django.core.cache import caches
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Evento


@receiver(pre_save, sender=User)
def sincronizar_username_com_email(sender, instance, **kwargs):
    if instance.email:
        instance.username = instance.email.lower()


@receiver(post_save, sender=Evento)
@receiver(post_delete, sender=Evento)
def limpar_cache_de_paginas(sender, **kwargs):
    # home, /eventos/ e as páginas de faceta (categoria/região/etc.) ficam em
    # cache_para_anonimos por até 180s (ver views.py). Sem isso, uma capa
    # reenviada ou um evento novo só apareceria pra visitante anônimo depois
    # da janela de cache expirar. Usa o alias "paginas", separado do
    # "default" que o rate limiting usa (ver settings/base.py) — limpar tudo
    # de uma vez zeraria contadores de tentativa de login, recuperação de
    # senha etc. antes da hora, e qualquer pessoa logada poderia burlar
    # esses limites só criando ou editando um evento.
    caches["paginas"].clear()
