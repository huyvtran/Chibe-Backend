# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.shortcuts import render
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from azienda.models import Partner
from django.conf import settings
from .tasks import send_all_push

IS_LOCAL = settings.IS_LOCAL

class staff_index(View):
	def dispatch(self, *args, **kwargs):
		return super(staff_index, self).dispatch(*args, **kwargs)

	def get(self, request, *args, **kwargs):

		template_name = "staff_index.html"
		return render(request, template_name)

	def post(self, request, *args, **kwargs):

		piva = request.POST.get("piva", "")
		codice = request.POST.get("codice", "")

		if codice == "ciao":
			p_ex = Partner.objects.filter(partita_iva = piva).exists()

			if p_ex:
				partner = Partner.objects.get(partita_iva = piva)
				partner.attivo = False
				partner.save()

				messages.success(request, "Partner bloccato con successo")
			else:
				messages.error(request, "Il partner non esiste")
		else:
			messages.error(request, "Codice errato")
			
		url = reverse('staff_index')
		return HttpResponseRedirect(url)

class staff_push(View):
	@method_decorator(staff_member_required)
	def dispatch(self, *args, **kwargs):
		return super(staff_push, self).dispatch(*args, **kwargs)

	def get(self, request, *args, **kwargs):

		template_name = "staff_push.html"
		return render(request, template_name)

	def post(self, request, *args, **kwargs):
		testo = request.POST['testo']

		if IS_LOCAL:
			send_all_push(testo)
		else:
			send_all_push.delay(testo)

		messages.success(request, "Messaggio inviato")

		url = reverse('staff_push')
		return HttpResponseRedirect(url)




