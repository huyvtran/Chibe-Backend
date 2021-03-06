# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.db.models import Sum
from main.models import Tribu, Utente, OrdineDesiderio
from datetime import date, datetime, timedelta
from haversine import haversine
from chibe.utils import get_percentuale

class ContrattoMarketing(models.Model):
	etichetta = models.CharField(blank = True, null = True, max_length=200)

	percentuale_marketing = models.FloatField(default = 0)

	inizio = models.DateField()
	fine = models.DateField()
	tacito_rinnovo = models.BooleanField(default = True)

	PERIODO_FATTURAZIONE = (
		("15", "15 giorni"),
		("30", "30 giorni"),
		("60", "60 giorni"),
		("90", "90 giorni"),
	)

	fatturazione = models.CharField(max_length = 3, choices = PERIODO_FATTURAZIONE, default = "15")	
	documentazione_traffico_acquisti = models.BooleanField(default = True)
	periodo_documentazione = models.CharField(max_length = 3, choices = PERIODO_FATTURAZIONE, default = "15")	

	def is_valid(self):
		fine = self.fine
		today = date.today()

		return today < fine

	def date_fatturazione(self):
		inizio = self.inizio
		fine = self.fine
		fatturazione = self.fatturazione

		delta = fine - inizio # timedelta

		list_date = []

		for i in range(delta.days + 1):
			x = i * int(fatturazione)
			data = (inizio + timedelta(days=x))
			if data < fine:
				list_date.append(data)

		list_date.append(fine)
		list_date = sorted(list_date)

		return list_date

	def __unicode__(self):
		etichetta = self.etichetta
		if etichetta:
			return etichetta
		else:
			return str(self.id)

	class Meta:
		verbose_name = "Contratto Marketing"
		verbose_name_plural = "2. Contratto Marketing"

class Categoria(models.Model):
	nome = models.CharField(max_length = 300)
	id_immagine = models.CharField(max_length = 300)

	def __unicode__(self):
		return self.nome	

	class Meta:
		verbose_name = "Categoria"
		verbose_name_plural = "4. Categorie"


class SearchQueryset(models.query.QuerySet):
	def search(self, lat, lon, limite):
		lat = float(lat)
		lon = float(lon)
		limite = float(limite)
		center_point = (lat, lon)

		result_list = []
		dict_distanza = {}
		now = datetime.now().date()

		for su in self:
			contratto = su.contratto
			attivo = su.attivo
			primario = su.primario
			if contratto and attivo and primario:

				is_valido = contratto.is_valid()
				if is_valido:
					point = (su.latitudine, su.longitudine)
					distanza = haversine(center_point, point)

					percentuale_marketing = contratto.percentuale_marketing
					percentuale = get_percentuale(percentuale_marketing)

					if isinstance(percentuale, basestring):
						percentuale_val = percentuale.replace('+', "")
						percentuale_val = int(percentuale_val)
					else:
						percentuale_val = percentuale

					if distanza < limite:

						importo = Acquisto.objects.filter(partner = su).aggregate(Sum('importo'))

						orsi = su.orsi
						aquile = su.aquile
						lupi = su.lupi
						puma = su.puma
						volpi = su.volpi
						tribu = su.tribu
						tribu_val = None
						if tribu:
							tribu_val = tribu.nome

						categoria_partner_val = ""
						if su.categoria_partner:
							categoria_partner_val = su.categoria_partner

						json_su = {
							"id" : su.id,
							"banner" : str(su.banner),
							"logo" : str(su.logo),
							"descrizione" : su.descrizione,
							"telefono" : su.telefono_fisso,
							"ragione_sociale" : su.ragione_sociale,
							"indirizzo" : su.indirizzo,
							"distanza" : distanza,
							"orsi" : orsi,
							"aquile" : aquile,
							"lupi" : lupi,
							"puma" : puma,
							"volpi" : volpi,
							"tribu" : tribu_val,
							"percentuale" : percentuale,
							"percentuale_val" : percentuale_val,
							"date_joined" : su.date_joined,
							"importo" : importo['importo__sum'],
							"categoria_partner" : categoria_partner_val
						}

						result_list.append(json_su)

		return result_list

class PartneroManager(models.Manager):
	def get_queryset(self):
		return SearchQueryset(self.model, using=self._db)

	def search(self, lat, lon, limite):
		return self.get_queryset().search(lat, lon, limite)

class Partner(User):
	objects_search = PartneroManager()
	ragione_sociale = models.CharField(max_length = 300, verbose_name = "Marchio")
	tripadvisor = models.CharField(max_length = 700, blank = True, null = True)
	codice_fiscale = models.CharField(max_length = 300)
	partita_iva = models.CharField(max_length = 300)
	indirizzo = models.CharField(max_length = 300)
	latitudine = models.FloatField()
	longitudine = models.FloatField()
	telefono_fisso = models.CharField(max_length = 300, )
	telefono_cellulare = models.CharField(max_length = 300, )
	descrizione = models.TextField()
	contratto = models.ForeignKey(ContrattoMarketing, blank = True, null = True)
	primario = models.BooleanField(default = True)

	# Dati fattura
	ragione_sociale_fattura = models.CharField(max_length = 300, blank = True, null = True)
	indirizzo_via_fattura = models.CharField(max_length = 300, blank = True, null = True)
	indirizzo_cap = models.CharField(max_length = 300, blank = True, null = True)
	indirizzo_citta = models.CharField(max_length = 300, blank = True, null = True)
	indirizzo_provincia = models.CharField(max_length = 300, blank = True, null = True)
	indirizzo_extra = models.CharField(max_length = 300, blank = True, null = True)
	fax = models.CharField(max_length = 300, blank = True, null = True)

	CATEGORIA_PARTNER = (
		("RIS", "Food"),
		("ABB", "Abbigliamento"),
		("BAR", "Bar"),
		("SPO", "Sport"),
		("TEC", "Gaming"),

		("OTT", "Ottica"),
		("GIO", "Gioielleria"),
		("LIB", "Librerie/Cartolerie"),
		("COL", "Collezionismo"),
		("INT", "Intrattenimento"),
		("EST", "Estetica/Benessere"),

	)

	categoria_partner = models.CharField(max_length = 3, choices = CATEGORIA_PARTNER, blank = True, null = True)	

	categorie = models.ManyToManyField(Categoria)


	logo = models.ImageField(upload_to="aziende/", blank = True, null = True)
	logo.help_text = "La dimensione deve essere 400x400 pixel"

	banner = models.ImageField(upload_to="aziende/", blank = True, null = True)
	banner.help_text = "La dimensione deve essere 400x100 pixel"

	attivo = models.BooleanField(default = True) 

	is_fornitore = models.BooleanField(default = False)
	tribu = models.ForeignKey(Tribu, blank = True, null = True)

	orsi = models.IntegerField(default=0)
	aquile = models.IntegerField(default=0)
	lupi = models.IntegerField(default=0)
	puma = models.IntegerField(default=0)
	volpi = models.IntegerField(default=0)	

	def __unicode__(self):
		return self.ragione_sociale

	class Meta:
		verbose_name = "Partner"
		verbose_name_plural = "1. Partners"

	@staticmethod
	def post_save(sender, **kwargs):
		instance = kwargs.get('instance')
		created = kwargs.get('created')
		username = instance.username

		if created:
			instance.set_password(username)
			instance.save()
		else:
			check_password = instance.check_password(username)
			if not check_password:
				instance.set_password(username)
				instance.save()				

post_save.connect(Partner.post_save, sender=Partner)

class Supervisore(models.Model):
	etichetta = models.CharField(max_length = 300, blank = True, null = True)
	descrizione = models.TextField(blank = True, null = True)
	token = models.CharField(max_length = 300, blank = True, null = True)
	partner = models.ManyToManyField(Partner)

	class Meta:
		verbose_name = "Supervisore"
		verbose_name_plural = "Supervisori"

class Acquisto(models.Model):
	categoria = models.ForeignKey(Categoria)
	importo = models.DecimalField(max_digits=10, decimal_places=2)
	partner = models.ForeignKey(Partner) 
	utente = models.ForeignKey(Utente) 
	timestamp = models.DateTimeField()
	#timestamp.editable=True

	def __unicode__(self):
		return str(self.importo)

	class Meta:
		verbose_name = "Acquisto"
		verbose_name_plural = "3. Acquisti"

class Fattura(models.Model):
	partner = models.ForeignKey(Partner)
	importo = models.DecimalField(max_digits=10, decimal_places=2, null = True, blank = True)
	periodo_iniziale = models.DateField()
	periodo_finale = models.DateField()

	class Meta:
		verbose_name = "Fattura"
		verbose_name_plural = "5. Fatture"




