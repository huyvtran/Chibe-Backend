# -*- coding: utf-8 -*-
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, HttpResponseNotFound, HttpResponseBadRequest
from chibe.email_system import email_reset_password
from chibe.push import notifica_amico, invia_punti_push
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.core import serializers
from datetime import datetime
from random import randint
from .models import Utente, OnBoard, Tribu, ResetPassword
from .models import Provincia, Scuola
from .models import Gruppo, PuntiGruppo, OrdineDesiderio
from .models import PushNotification
from .models import Invito
from .tasks import check_sku_groups
from social_django.models import UserSocialAuth
from django.conf import settings
import StringIO
from PIL import Image
from django.db.models import Q
import hashlib
import wget

AVATAR_MEDIA_ROOT = settings.MEDIA_ROOT + "/avatar"
PUNTI_BONUS = 100

def check_connected(request):
	if request.user.is_authenticated:

		username = request.user.username
		utente = Utente.objects.get(username = username)
		onboard = OnBoard.objects.get(utente = utente)

		is_social = UserSocialAuth.objects.filter(user_id = request.user.id).exists()

		if is_social:
			tipo_utente = "social"

			complete = onboard.fb_complete
			fb_step_1 = onboard.fb_step_1
			fb_step_2 = onboard.fb_step_2

			if complete:
				output = 0
			elif not fb_step_1:
				output = 1
			elif not fb_step_2:
				output = 2
		else:
			tipo_utente = "regular"

			complete = onboard.complete
			step_1 = onboard.step_1
			step_2 = onboard.step_2
			step_3 = onboard.step_3

			if complete:
				output = 0
			elif not step_1:
				output = 1
			elif not step_2:
				output = 2
			elif not step_3:
				output = 3

		json_output = {
			"tipo": tipo_utente,
			"output": output
		}

		return JsonResponse(json_output)
	else:
		return HttpResponse('Unauthorized', status=401)

class utente_login(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_login, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		username = request.POST.get("username", None)
		password = request.POST.get("password", None)

		user = authenticate(request, username=username, password=password)
		if user is not None:
			login(request, user)

			utente = Utente.objects.get(username = username)
			onboard = OnBoard.objects.get(utente = utente)

			complete = onboard.complete
			step_1 = onboard.step_1
			step_2 = onboard.step_2
			step_3 = onboard.step_3

			if complete:
				output = 0
			elif not step_1:
				output = 1
			elif not step_2:
				output = 2
			elif not step_3:
				output = 3

			json_output = {
				"tipo": "regular",
				"output": output
			}


			inv_ex = Invito.objects.filter(invitato = utente, redeemed = False).exists()
			if inv_ex:
				invito = Invito.objects.filter(invitato = utente, redeemed = False).first()

				# Punti al nuovo
				utente_nuovo_punti = utente.punti
				utente.punti = utente_nuovo_punti + PUNTI_BONUS
				utente.save()

				# Check sull host
				host = invito.host
				utente_punti_vecchi = host.punti

				num_inviti_host = Invito.objects.filter(host = host).count()

				if (utente_punti_vecchi < 1000) and (num_inviti_host < 11):
					host.punti = utente_punti_vecchi + PUNTI_BONUS
					host.save()

					notifica_amico(host, PUNTI_BONUS)

			return JsonResponse(json_output)
		else:
			return HttpResponse('Unauthorized', status=401)

class utente_forgot_password(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_forgot_password, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		email = request.POST.get("email", None)

		user = get_object_or_404(Utente, email=email)
		now = str(datetime.now()) + email
		token = hashlib.sha224(now).hexdigest()

		ResetPassword.objects.create(
			user = user,
			token = token
		)

		email_reset_password(email, token)

		return HttpResponse()

class utente_forgot_password_token(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_forgot_password_token, self).dispatch(*args, **kwargs)

	def get(self, request, token, *args, **kwargs):

		r = get_object_or_404(ResetPassword, token=token)

		args = {
			"r" : r
		}

		template_name = "utente_forgot_password_token.html"
		return render(request, template_name, args)

	def post(self, request, token, *args, **kwargs):
		r = get_object_or_404(ResetPassword, token=token)

		password = request.POST['password']
		password2 = request.POST['password2']
		if password != password2:
			
			messages.error(request, "Le password inserite non coincidono")
			url = reverse('utente_forgot_password_token', kwargs = {'token': token})
			return HttpResponseRedirect(url)

		user = r.user
		user.set_password(password)
		user.save()

		r.used = True
		r.save()
		
		messages.success(request, "Password reimpostata con successo")
		url = reverse('utente_forgot_password_token', kwargs = {'token': token})
		return HttpResponseRedirect(url)

class utente_register(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_register, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		username = request.POST.get("username", None)
		email = request.POST.get("email", None)

		email = email.strip()
		username = username.strip()
		
		email = email.lower()

		username_ex = Utente.objects.filter(username = username).exists()
		if username_ex:
			return HttpResponseBadRequest("Username già in uso")

		email_ex = Utente.objects.filter(email = email).exists()
		if email_ex:
			return HttpResponseBadRequest("Email già in uso")


		password_1 = request.POST.get("password_1", None)
		password_2 = request.POST.get("password_2", None)

		if password_1 != password_2:
			return HttpResponseBadRequest("Le due password non coincidono")


		codice = generate_code()

		utente_obj = Utente.objects.create_user(
			username = username,
			email = email,
			password = password_1,
			codice = codice
		)

		OnBoard.objects.create(utente = utente_obj)

		user = authenticate(request, username=username, password=password_1)

		if user is not None:
			login(request, user)		

		return HttpResponse()

def generate_code():
	code = randint(100000000, 999999999)

	while Utente.objects.filter(codice = str(code)).exists():
		code = randint(100000000, 999999999)

	return code 

def generate_code_ordine():
	code = randint(100000000, 999999999)

	while OrdineDesiderio.objects.filter(token = str(code)).exists():
		code = randint(100000000, 999999999)

	return code 

class utente_step1(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_step1, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		nome = request.POST['nome']
		cognome = request.POST['cognome']
		cellulare = request.POST['cellulare']

		utente.first_name = nome
		utente.last_name = cognome
		utente.telefono_cellulare = cellulare
		utente.save()

		onboard_obj = OnBoard.objects.get(utente = utente)
		onboard_obj.step_1 = True
		onboard_obj.save()

		return HttpResponse()

class utente_step1_fb(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_step1_fb, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		cellulare = request.POST['cellulare']
		username = request.POST['username']

		username_ex = Utente.objects.filter(username = username).exists()
		if username_ex:
			return HttpResponseBadRequest("Username già in uso")

		utente.telefono_cellulare = cellulare
		utente.username = username
		utente.save()

		onboard_obj = OnBoard.objects.get(utente = utente)
		onboard_obj.fb_step_1 = True
		onboard_obj.save()

		return HttpResponse()

class utente_step2(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_step2, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		avatar = request.POST.get("avatar", None)
		utente.avatar = avatar
		utente.save()

		onboard_obj = OnBoard.objects.get(utente = utente)
		onboard_obj.step_2 = True
		onboard_obj.save()

		return HttpResponse()

class utente_province(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_province, self).dispatch(*args, **kwargs)

	def get(self, request, *args, **kwargs):

		province = Provincia.objects.filter(attivo = True)
		data = serializers.serialize('json', province, fields=('id', 'nome', 'codice'))

		return HttpResponse(data)

class utente_province_id(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_province_id, self).dispatch(*args, **kwargs)

	def get(self, request, id, *args, **kwargs):

		provincia = Provincia.objects.get(pk = id)

		scuole = Scuola.objects.filter(provincia = provincia)
		data = serializers.serialize('json', scuole, fields=('id', 'nome'))

		return HttpResponse(data)

class utente_step3(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_step3, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		provincia_id = request.POST['provincia_id']
		provincia = Provincia.objects.get(pk = provincia_id)

		scuola_id = request.POST['scuola_id']
		scuola = Scuola.objects.get(pk = scuola_id)

		classe = request.POST.get("classe", None)
		newsletter = request.POST.get("newsletter", None)

		sesso = request.POST.get('sesso', "M")
		compleanno = request.POST.get('compleanno', None)
		if compleanno:
			compleanno_obj = datetime.strptime(compleanno, '%Y-%M-%d').date()
		else:
			compleanno_obj = datetime.strptime("1970-01-01", '%Y-%M-%d').date()

		utente.compleanno = compleanno_obj
		utente.sesso = sesso

		utente.classe = classe
		utente.provincia = provincia
		utente.scuola = scuola
		utente.save()

		onboard_obj = OnBoard.objects.get(utente = utente)
		onboard_obj.step_3 = True
		onboard_obj.fb_step_2 = True
		onboard_obj.fb_complete = True
		onboard_obj.complete = True
		onboard_obj.save()

		return HttpResponse()

@csrf_exempt
def upload_picture(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	f = request.FILES['file']

	str = ""
	for c in f.chunks():
		str += c
	imagefile  = StringIO.StringIO(str)
	image = Image.open(imagefile)

	token = utente.codice
	#token = str(token)

	outfile = AVATAR_MEDIA_ROOT + '/' + token + '.jpg'
	image.save(outfile, "JPEG")	

	output = "/media/avatar/" + token + '.jpg'

	return HttpResponse(output)

def get_code(request):
	user = request.user
	username = user.username

	utente = Utente.objects.get(username = username)
	codice = utente.codice
	return HttpResponse(codice)

def search_amico(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	amico = request.GET.get("amico", None)

	amici = utente.amici.filter().values_list("id", flat = True)

	utenti = Utente.objects.filter(
		Q(email__icontains=amico) |
		Q(first_name__icontains=amico) |
		Q(last_name__icontains=amico) |
		Q(username__icontains=amico) |
		Q(telefono_cellulare__icontains=amico) |
		Q(codice__icontains=amico)
	).exclude(username = username).exclude(pk__in=amici).values("username", "id", "first_name", "last_name", "avatar")

	return JsonResponse(list(utenti), safe = False)

def utente_amici(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	amici = utente.amici.all().values("username", "id", "first_name", "last_name", "punti", "avatar")

	return JsonResponse(list(amici), safe = False)

@csrf_exempt
def utente_amico_add(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	id_amico = request.POST['id_amico']
	amico = Utente.objects.get(pk = id_amico)

	utente.amici.add(amico)

	return HttpResponse()

@csrf_exempt
def utente_amico_delete(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	id_amico = request.POST['id_amico']
	amico = Utente.objects.get(pk = id_amico)

	utente.amici.remove(amico)

	return HttpResponse()

@csrf_exempt
def utente_info(request):
	user = request.user
	username = user.username

	utente = Utente.objects.get(username = username)

	modifica_tribu = None

	tribu_timestamp = utente.tribu_timestamp
	if tribu_timestamp:
		now = datetime.now().date()
		diff = now - tribu_timestamp
		days = diff.days
		if days >= 60:
			modifica_tribu = True


	tribu = utente.tribu
	tribu_name = None
	if tribu:
		tribu_name = tribu.nome

	json_utente = {
		"id" : utente.id,
		"avatar" : utente.avatar,
		"username" : utente.username,
		"descrizione" : utente.descrizione,
		"nome" : utente.first_name,
		"cognome" : utente.last_name,
		"punti" : utente.punti,
		"tribu" : tribu_name,
		"modifica_tribu" : modifica_tribu,
		"sesso" : utente.sesso
	}

	return JsonResponse(json_utente)	

@csrf_exempt
def utente_tribu(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	tribu = request.POST['tribu']

	tribu_obj = Tribu.objects.get(nome__iexact = tribu)
	tribu_timestamp = datetime.now().date()

	utente.tribu = tribu_obj
	utente.tribu_timestamp = tribu_timestamp
	utente.save()

	return HttpResponse()

@csrf_exempt
def utente_modifica(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	descrizione = request.POST['descrizione']

	utente.descrizione = descrizione
	utente.save()


	return HttpResponse()

@csrf_exempt
def utente_desideri(request):
	user = request.user
	username = user.username

	utente = Utente.objects.get(username = username)

	gruppi = Gruppo.objects.filter(utenti = utente)

	list_gruppi = []

	for gruppo in gruppi:

		utente_admin = gruppo.utente_admin
		admin = False
		if utente == utente_admin:
			admin = True

		utenti = gruppo.utenti.all().values("id")

		punti_necessari = float(gruppo.desiderio.costo_riscatto) / 0.001;
		punti = float(gruppo.punti)
	
		percentuale = int((punti / punti_necessari) * 100)
		percentuale = str(percentuale) + "%"

		gruppo_json = {
			"id" : gruppo.id,
			"punti" : punti,
			"punti_necessari" : punti_necessari,
			"admin" : admin,
			"utenti" : list(utenti),
			"nome" : gruppo.desiderio.nome,
			"num_gruppo" : gruppo.desiderio.num_gruppo,
			"percentuale" : percentuale
		}

		ordine_ex = OrdineDesiderio.objects.filter(gruppo = gruppo, ritirato = True).exists()
		if not ordine_ex:
			list_gruppi.append(gruppo_json)

	return JsonResponse(list_gruppi, safe = False)

def utente_punti(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)
	punti = utente.punti

	return HttpResponse(punti)	

@csrf_exempt
def utente_inviapunti(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)

	amico_id = request.POST['amico_id']
	amico = Utente.objects.get(pk = amico_id)

	punti = request.POST['punti']
	punti = int(punti)

	utente_punti_old = utente.punti
	utente_punti_new = utente_punti_old - punti
	utente.punti = utente_punti_new
	utente.save()

	amico_punti_old = amico.punti
	amico_punti_new = amico_punti_old + punti
	amico.punti = amico_punti_new
	amico.save()

	invia_punti_push(username, punti, amico)

	return HttpResponse()

class utente_gruppo(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_gruppo, self).dispatch(*args, **kwargs)

	def get(self, request, id, *args, **kwargs):	
		user = request.user
		username = user.username

		utente = Utente.objects.get(username = username)

		gruppo = Gruppo.objects.select_related('desiderio').get(pk = id)

		list_gruppi = []

		utente_admin = gruppo.utente_admin
		admin = False
		if utente == utente_admin:
			admin = True

		utenti = gruppo.utenti.all().values("id")

		miei_punti = utente.punti
		ordine_riscattato = OrdineDesiderio.objects.filter(gruppo = gruppo).exists()
		codice_ordine = None
		ritirato = False
		partners = []
		if ordine_riscattato:
			ordine_obj = OrdineDesiderio.objects.get(gruppo = gruppo)
			partners = gruppo.desiderio.partners.all().values("ragione_sociale", "indirizzo")
			partners = list(partners)
			codice_ordine = ordine_obj.token
			ritirato = ordine_obj.ritirato

		punti_necessari = float(gruppo.desiderio.costo_riscatto) / 0.001;
		punti = float(gruppo.punti)
	
		percentuale = int((punti / punti_necessari) * 100)
		percentuale = str(percentuale) + "%"			

		gruppo_json = {
			"id" : gruppo.id,
			"punti" : gruppo.punti,
			"punti_necessari" : gruppo.desiderio.punti_piuma(),
			"admin" : admin,
			"utenti" : list(utenti),
			"nome" : gruppo.desiderio.nome,
			"num_gruppo" : gruppo.desiderio.num_gruppo,
			"miei_punti" : miei_punti,
			"conquistato" : gruppo.is_conquistato(),
			"ordine_riscattato" : ordine_riscattato,
			"codice_ordine" : codice_ordine,
			"partners" : partners,
			"ritirato" : ritirato,
			"percentuale" : percentuale,
			"descrizione" : gruppo.desiderio.descrizione_breve,
			"immagine" : str(gruppo.desiderio.immagine),
		}

		list_gruppi.append(gruppo_json)

		return JsonResponse(gruppo_json, safe = False)

	def post(self, request, id, *args, **kwargs):
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		gruppo = Gruppo.objects.select_related('desiderio').get(pk = id)

		punti_piuma = request.POST['punti_piuma']
		punti_piuma = int(punti_piuma)

		punti_del_gruppo = gruppo.punti
		desiderio = gruppo.desiderio
		punti_piuma_desiderio = desiderio.punti_piuma()

		delta_punti = punti_piuma_desiderio - punti_del_gruppo

		if delta_punti < punti_piuma:
			punti_piuma = delta_punti

		PuntiGruppo.objects.create(gruppo = gruppo, utente = utente, punti = punti_piuma)

		utente_old_punti = utente.punti
		utente_punti_new = utente_old_punti - punti_piuma
		utente.punti = utente_punti_new
		utente.save()

		gruppo_old_punti = gruppo.punti
		gruppo_new_punti = gruppo_old_punti + punti_piuma
		gruppo.punti = gruppo_new_punti
		gruppo.save()

		return HttpResponse()

class utente_gruppo_riscatta(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_gruppo_riscatta, self).dispatch(*args, **kwargs)

	def post(self, request, id, *args, **kwargs):	
		user = request.user
		username = user.username

		utente = Utente.objects.get(username = username)

		gruppo = Gruppo.objects.get(pk = id)
		desiderio = gruppo.desiderio
		current_sku = desiderio.sku

		if current_sku > 0:		
			ordine_ex = OrdineDesiderio.objects.filter(gruppo = gruppo).exists()

			if not ordine_ex:
				token = generate_code_ordine()
				OrdineDesiderio.objects.create(gruppo = gruppo, token = token)

			#abbassa la SKU
			new_sku = current_sku - 1
			desiderio.sku = new_sku
			desiderio.save()

			#controlla gli altri seguitori
			if new_sku == 0:
				#check_sku_groups(gruppo.id, desiderio)
				check_sku_groups.delay(gruppo.id, desiderio)

		else:
			print "Fai qualcosa"

		return HttpResponse()

class utente_gruppo_rimuovi(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_gruppo_rimuovi, self).dispatch(*args, **kwargs)

	def post(self, request, id, *args, **kwargs):	
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		gruppo = Gruppo.objects.get(pk = id)
		utente_admin = gruppo.utente_admin

		if utente.id == utente_admin.id:
			gruppo.delete()
		else:
			gruppo.utenti.remove(utente)

		return HttpResponse()


class utente_gruppo_utenti(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_gruppo_utenti, self).dispatch(*args, **kwargs)

	def get(self, request, id, *args, **kwargs):	
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		gruppo = Gruppo.objects.get(pk = id)

		list_gruppi = []

		utente_admin = gruppo.utente_admin
		admin = False
		if utente == utente_admin:
			admin = True

		utenti_gruppo = gruppo.utenti.all()
		amici_miei = utente.amici.all()
		amici_nogruppo = amici_miei.exclude(pk__in = utenti_gruppo)

		utenti_gruppo = utenti_gruppo.values("id", "username", "first_name", "last_name", "avatar")
		amici_nogruppo = amici_nogruppo.values("id", "username", "first_name", "last_name", "avatar")

		gruppo_json = {
			"io" : utente.id,
			"id" : gruppo.id,
			"punti" : gruppo.punti,
			"punti_necessari" : gruppo.desiderio.costo_riscatto,
			"admin" : admin,
			"utenti" : list(utenti_gruppo),
			"amici" : list(amici_nogruppo),
			"nome" : gruppo.desiderio.nome,
			"num_gruppo" : gruppo.desiderio.num_gruppo
		}

		list_gruppi.append(gruppo_json)

		return JsonResponse(gruppo_json, safe = False)

	def post(self, request, id, *args, **kwargs):
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		gruppo = Gruppo.objects.get(pk = id)

		amico_id = request.POST['amico_id']
		amico = Utente.objects.get(pk = amico_id)

		gruppo.utenti.add(amico)

		return HttpResponse()

class utente_register_push(View):
	@method_decorator(csrf_exempt)
	def dispatch(self, *args, **kwargs):
		return super(utente_register_push, self).dispatch(*args, **kwargs)

	def post(self, request, *args, **kwargs):
		user = request.user
		username = user.username
		utente = Utente.objects.get(username = username)

		sistema_operativo = request.POST['sistema_operativo']
		token = request.POST['token']

		exists_push_so = PushNotification.objects.filter(utente = utente, sistema_operativo = sistema_operativo).exists()
		if exists_push_so:
			PushNotification.objects.filter(utente = utente, sistema_operativo = sistema_operativo).update(token = token)
		else:
			p_ex = PushNotification.objects.filter(utente = utente, sistema_operativo = sistema_operativo, token = token).exists()

			if not p_ex:
				PushNotification.objects.create(
					utente = utente,
					sistema_operativo = sistema_operativo,
					token = token
				)

		return HttpResponse("")


from django.contrib.auth import login
from social_django.utils import psa
from social_core.backends.google import GooglePlusAuth
from social_core.utils import handle_http_errors
from google.oauth2 import id_token
from google.auth.transport import requests
import requests as requests2

CLIENT_ID = settings.SOCIAL_AUTH_GOOGLE_PLUS_KEY

class CustomGooglePlusAuth(GooglePlusAuth):

	DEFAULT_SCOPE = [
		'https://www.googleapis.com/auth/plus.login',
		'https://www.googleapis.com/auth/plus.me',
		'email'
	]

	def user_data(self, access_token, *args, **kwargs):
		idinfo = id_token.verify_oauth2_token(access_token, requests.Request(), CLIENT_ID)
		if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
			raise ValueError('Wrong issuer.')
		return idinfo

	@handle_http_errors
	def do_auth(self, access_token, *args, **kwargs):
		"""Finish the auth process once the access_token was retrieved"""
		res = kwargs.get('response')

		account_details = False
		try:
			data = self.user_data(access_token, *args, **kwargs)
		except:
			id_token = res['id_token']
			data = self.user_data(id_token, *args, **kwargs)
			account_details_request = requests2.get('https://www.googleapis.com/plus/v1/people/me?access_token=' + access_token)
			account_details = account_details_request.json()	

		response = kwargs.get('response') or {}
		response.update(data or {})
		if account_details:
			name = account_details['name']
			givenName = name['givenName']
			familyName = name['familyName']

			image = account_details['image']
			picture = image['url']

			response['family_name'] = familyName
			response['given_name'] = givenName
			response['picture'] = picture
			#given_name
			#family_name
			#picture

		if 'access_token' not in response:
			response['access_token'] = access_token
		kwargs.update({'response': response, 'backend': self})
		return self.strategy.authenticate(*args, **kwargs)

@psa('social:complete')
def register_by_access_token(request, backend):
	token = request.GET.get('access_token')
	user = request.backend.do_auth(token, ajax = True)

	if user:
		login(request, user)

		username = request.user.username
		utente = Utente.objects.get(username = username)
		onboard = OnBoard.objects.get(utente = utente)

		tipo_utente = "social"

		complete = onboard.fb_complete
		fb_step_1 = onboard.fb_step_1
		fb_step_2 = onboard.fb_step_2

		if complete:
			output = 0
		elif not fb_step_1:
			output = 1
		elif not fb_step_2:
			output = 2

		json_output = {
			"tipo": tipo_utente,
			"output": output
		}

		return JsonResponse(json_output)


import logging
logger = logging.getLogger('django')

def register_social(backend, user, response, strategy, *args, **kwargs):

	backend_name = backend.name
	if backend_name == "google-plus":
		email = response['email']
		first_name = response['given_name']
		last_name = response['family_name']

		url_avatar = response['picture']

	elif backend_name == "facebook":
		url_avatar = "http://graph.facebook.com/%s/picture?type=large"%response['id']
		first_name = response['first_name']
		last_name = response['last_name']
		email = response.get("email", None)

	if email:
		user.email = email
		
	user.first_name = first_name
	user.last_name = last_name
	user.save()		

	member_exists = Utente.objects.filter(user_ptr = user).exists()

	if member_exists:
		member = Utente.objects.get(user_ptr = user)
	else:
		member = Utente(user_ptr = user)
		member.__dict__.update(user.__dict__)
		
		codice = generate_code()
		member.codice = codice
		member.save()

		OnBoard.objects.create(utente = member)

	token = member.codice
	token = str(token)

	outfile = AVATAR_MEDIA_ROOT + '/' + token + '.jpg'

	wget.download(url_avatar, out=outfile)
	output = "/media/avatar/" + token + '.jpg'
	member.avatar = output

	member.save()

	if not member_exists:
		user_code = strategy.session_get('user_code')
		if user_code:
			#Punti al nuovo		
			pp_nuovo = PUNTI_BONUS
			utente_obj_punti_vecchi = member.punti
			member.punti = utente_obj_punti_vecchi + pp_nuovo 
			member.save()

			#Punti al vecchio
			utente = get_object_or_404(Utente, codice=user_code)

			pp_vecchio = PUNTI_BONUS
			utente_punti_vecchi = utente.punti
			utente.punti = utente_punti_vecchi + pp_vecchio
			utente.save()

			notifica_amico(utente, PUNTI_BONUS)

from .forms import NameForm
class utente_invito(View):
	def dispatch(self, *args, **kwargs):
		return super(utente_invito, self).dispatch(*args, **kwargs)

	def get(self, request, token, *args, **kwargs):
		utente = get_object_or_404(Utente, codice=token)

		form = NameForm()

		args = {
			"utente" : utente,
			"token" : token,
			"CLIENT_ID": CLIENT_ID,
			"form" : form
		}

		template_name = "utente_invito.html"
		return render(request, template_name, args)

	def post(self, request, token, *args, **kwargs):
		utente = get_object_or_404(Utente, codice=token)

		form = NameForm(request.POST)

		if form.is_valid():
			username = form.cleaned_data['username']
			email = form.cleaned_data['email']

			password_1 = form.cleaned_data['password_1']
			password_2 = form.cleaned_data['password_2']
		else:
			args = {
				"utente" : utente,
				"token" : token,
				"CLIENT_ID": CLIENT_ID,
				"form" : form
			}

			template_name = "utente_invito.html"
			return render(request, template_name, args)			

		email = email.strip()
		username = username.strip()
		
		email = email.lower()

		username_ex = Utente.objects.filter(username = username).exists()
		if username_ex:
			messages.error(request, "Username già in uso")
			url = reverse('utente_invito', kwargs = {'token': token})
			return HttpResponseRedirect(url)

		email_ex = Utente.objects.filter(email = email).exists()
		if email_ex:
			messages.error(request, "Email già in uso")
			url = reverse('utente_invito', kwargs = {'token': token})
			return HttpResponseRedirect(url)

		if password_1 != password_2:
			messages.error(request, "Le due password non coincidono")
			url = reverse('utente_invito', kwargs = {'token': token})
			return HttpResponseRedirect(url)

		codice = generate_code()

		utente_obj = Utente.objects.create_user(
			username = username,
			email = email,
			password = password_1,
			codice = codice
		)

		OnBoard.objects.create(utente = utente_obj)

		Invito.objects.create(
			invitato = utente_obj,
			host = utente
		)

		args = {
			"success" : True,
			"punti" : PUNTI_BONUS
		}

		template_name = "utente_invito.html"
		return render(request, template_name, args)

def successo_invito(request):
	args = {
		"success" : True,
		"punti" : PUNTI_BONUS
	}

	template_name = "utente_invito.html"
	return render(request, template_name, args)

def utente_invitecode(request):
	user = request.user
	username = user.username
	utente = Utente.objects.get(username = username)
	codice = utente.codice
	return HttpResponse(codice)

from django.contrib.sessions.models import Session
from django.contrib.auth.models import User

@csrf_exempt
def utente_session(request):
	session_key = request.session.session_key

	#logger.debug(session_key)

	return HttpResponse(session_key)

@csrf_exempt
def utente_set_session(request):
	session_key = request.POST['session_key']

	session_esistenza = Session.objects.filter(session_key=session_key).exists()
	if session_esistenza:
		session = Session.objects.get(session_key=session_key)
		uid = session.get_decoded().get('_auth_user_id')
		user_esistenza = User.objects.filter(pk=uid).exists()
		if user_esistenza:
			user = User.objects.get(pk=uid)
			login(request, user)
			return HttpResponse('La session corrisponde alla email')
		else:
			return HttpResponseBadRequest('Errore: non riesco ad ottenere il nome utente')
	else:
		return HttpResponseBadRequest('Errore: la session non esiste')

from azienda.tasks import check_premiospeciale
def utente_test(request):

	check_premiospeciale()

	return HttpResponse()











