from django.contrib.auth.models import User
from django.core.cache import cache
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
    # da janela de cache expirar. O cache de páginas usa o alias "default",
    # o mesmo do rate limiting — limpar tudo reseta contadores de tentativa
    # antes da hora, mas isso é só cosmético (não é um problema de segurança
    # prático) e evita a complexidade de um cache separado só pra isso.
    cache.clear()
