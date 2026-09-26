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

    caches["paginas"].clear()
