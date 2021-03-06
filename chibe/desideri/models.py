# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db import models

class CategoriaDesiderio(models.Model):
	nome = models.CharField(max_length = 300)
	id_immagine = models.CharField(max_length = 300)
	descrizione = models.TextField(blank = True, null = True)

	def __unicode__(self):
		return self.nome	

	class Meta:
		verbose_name = "Categoria desiderio"
		verbose_name_plural = "2. Categorie desiderio"	

class Desiderio(models.Model):
	nome = models.CharField(max_length = 300, blank = True, null = True)
	descrizione_breve = models.TextField(blank = True, null = True)
	descrizione_lunga = models.TextField(blank = True, null = True)
	
	costo_acquisto = models.DecimalField(max_digits=10, decimal_places=2)
	costo_listino = models.DecimalField(max_digits=10, decimal_places=2)
	costo_riscatto = models.DecimalField(max_digits=10, decimal_places=2)

	#immagine = models.CharField(max_length = 300, blank = True, null = True)
	immagine = models.ImageField(blank = True, null = True, upload_to="desideri/")
	immagine.help_text = "La dimensione deve essere 400x100 pixel"

	big_picture = models.ImageField(blank = True, null = True, upload_to="desideri/")
	big_picture.help_text = "La dimensione deve essere 400x400 pixel"

	categoria = models.ForeignKey(CategoriaDesiderio)
	data_inizio = models.DateField()
	data_fine = models.DateField()
	in_evidenza = models.BooleanField(default = False)
	sku = models.IntegerField()

	indirizzo = models.CharField(max_length = 300, blank = True, null = True)

	partners = models.ManyToManyField("azienda.Partner", blank = True)

	codice = models.CharField(max_length = 300, blank = True, null = True)
	num_gruppo = models.IntegerField()

	def __unicode__(self):
		return self.nome

	def punti_piuma(self):
		return float(self.costo_riscatto) / 0.001

	class Meta:
		verbose_name = "Desiderio"
		verbose_name_plural = "1. Desideri"	

class PremioSpeciale(models.Model):
	nome = models.CharField(max_length = 300, blank = True, null = True)
	sku = models.IntegerField()

	partner = models.ForeignKey("azienda.Partner", unique=True)

	class Meta:
		verbose_name='Premio speciale'
		verbose_name_plural='Premi speciali'


class AcquistoSpeciale(models.Model):
	premio = models.ForeignKey(PremioSpeciale)
	timestamp = models.DateTimeField(auto_now_add = True)
	#timestamp.editable=True

	class Meta:
		verbose_name = "Acquisto premio speciale"
		verbose_name_plural = "Acquisti premi speciali"



