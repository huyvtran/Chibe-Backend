# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.contrib import admin

from .models import Utente, OnBoard, Provincia, Scuola

@admin.register(Utente)
class UtenteAdmin(admin.ModelAdmin):
	list_display = ['username', 'codice', 'email', 'first_name', 'last_name', 'telefono_cellulare', 'provincia', 'scuola', 'classe']

@admin.register(OnBoard)
class OnBoardAdmin(admin.ModelAdmin):
	list_display = ['utente', 'step_1', 'step_2', 'step_3', 'complete']

@admin.register(Provincia)
class ProvinciaAdmin(admin.ModelAdmin):
	pass

@admin.register(Scuola)
class ScuolaAdmin(admin.ModelAdmin):
	pass