from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Evento, Gestion, PreferenciasUsuario


class BaseApiTestCase(APITestCase):
    """Dos usuarios con token, para probar también el aislamiento entre ellos."""

    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@test.com", "Clave-segura-123")
        self.otro = User.objects.create_user("luis", "luis@test.com", "Clave-segura-123")
        self.autenticar(self.user)

    def autenticar(self, usuario):
        token, _ = Token.objects.get_or_create(user=usuario)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def crear_evento(self, usuario=None, nombre="Boda"):
        return Evento.objects.create(
            nombre=nombre,
            fecha="2026-12-01",
            usuario=usuario or self.user,
        )

    def crear_gestion(self, evento, fecha="2026-10-12", horas="2", estado="pendiente",
                      nombre="Gestión", hora="09:00"):
        return Gestion.objects.create(
            evento=evento, nombre=nombre, fecha=fecha, hora=hora,
            horas=Decimal(horas), estado=estado,
        )


class PreferenciasTests(BaseApiTestCase):
    url = "/api/preferencias/"

    def test_get_crea_preferencias_con_6_horas_por_defecto(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(str(res.data["limite_horas"])), Decimal("6"))
        self.assertTrue(PreferenciasUsuario.objects.filter(usuario=self.user).exists())

    def test_patch_guarda_el_limite(self):
        res = self.client.patch(self.url, {"limite_horas": "8.5"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            PreferenciasUsuario.de_usuario(self.user).limite_horas, Decimal("8.50")
        )

    def test_acepta_los_extremos_1_y_12(self):
        for valor in ("1", "12"):
            res = self.client.patch(self.url, {"limite_horas": valor}, format="json")
            self.assertEqual(res.status_code, 200, valor)

    def test_rechaza_limite_fuera_de_1_a_12(self):
        for valor in ("0", "0.5", "12.5", "13", "-3"):
            res = self.client.patch(self.url, {"limite_horas": valor}, format="json")
            self.assertEqual(res.status_code, 400, valor)
            self.assertIn("limite_horas", res.data["error"]["details"])
        self.assertEqual(PreferenciasUsuario.de_usuario(self.user).limite_horas, Decimal("6"))

    def test_cada_usuario_tiene_su_limite(self):
        self.client.patch(self.url, {"limite_horas": "10"}, format="json")
        self.autenticar(self.otro)
        res = self.client.get(self.url)
        self.assertEqual(Decimal(str(res.data["limite_horas"])), Decimal("6"))

    def test_put_no_esta_permitido(self):
        res = self.client.put(self.url, {"limite_horas": "8"}, format="json")
        self.assertEqual(res.status_code, 405)

    def test_requiere_autenticacion(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_rechaza_valores_que_no_avanzan_de_media_hora(self):
        for valor in ("1.25", "4.25", "6.75", "11.99"):
            res = self.client.patch(
                self.url,
                {"limite_horas": valor},
                format="json",
            )
            self.assertEqual(res.status_code, 400, valor)


class LimiteDelEventoTests(BaseApiTestCase):
    def payload(self, **extra):
        data = {
            "nombre": "Cumpleaños",
            "fecha": "2026-12-20",
            "gestiones": [
                {
                    "nombre": "Torta",
                    "fecha": "2026-12-10",
                    "hora": "10:00",
                    "horas": "2",
                }
            ],
        }
        data.update(extra)
        return data

    def test_crear_evento_no_requiere_limite_propio(self):
        res = self.client.post(
            "/api/eventos/", self.payload(), format="json"
        )
        self.assertEqual(res.status_code, 201)
        self.assertFalse(
            hasattr(Evento.objects.get(), "limite_horas")
        )

    def test_crear_evento_no_cambia_preferencias_del_usuario(self):
        self.client.patch(
            "/api/preferencias/",
            {"limite_horas": "9"},
            format="json",
        )

        res = self.client.post(
            "/api/eventos/", self.payload(), format="json"
        )

        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            PreferenciasUsuario.de_usuario(self.user).limite_horas,
            Decimal("9.00"),
        )

    def test_limite_enviado_al_evento_no_modifica_preferencias(self):
        self.client.patch(
            "/api/preferencias/",
            {"limite_horas": "6"},
            format="json",
        )

        res = self.client.post(
            "/api/eventos/",
            self.payload(limite_horas="7.5"),
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            PreferenciasUsuario.de_usuario(self.user).limite_horas,
            Decimal("6.00"),
        )

    def test_editar_evento_no_cambia_el_limite_global(self):
        evento = self.crear_evento()

        self.client.patch(
            "/api/preferencias/",
            {"limite_horas": "8"},
            format="json",
        )

        res = self.client.patch(
            f"/api/eventos/{evento.id}/",
            {"nombre": "Boda actualizada"},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            PreferenciasUsuario.de_usuario(self.user).limite_horas,
            Decimal("8.00"),
        )

class HorasDeGestionTests(BaseApiTestCase):
    def setUp(self):
        super().setUp()
        self.evento = self.crear_evento()

    def nueva(self, horas):
        return self.client.post(
            f"/api/eventos/{self.evento.id}/subtareas/",
            {"nombre": "Música", "fecha": "2026-10-20", "hora": "18:00", "horas": horas},
            format="json",
        )

    def test_acepta_de_0_5_a_8(self):
        for valor in ("0.5", "4", "8"):
            self.assertEqual(self.nueva(valor).status_code, 201, valor)

    def test_rechaza_fuera_de_0_5_a_8(self):
        for valor in ("0", "0.25", "0.4", "8.5", "9", "-1"):
            res = self.nueva(valor)
            self.assertEqual(res.status_code, 400, valor)
            self.assertIn("horas", res.data["error"]["details"])

    def test_patch_de_horas_tambien_valida(self):
        gestion = self.crear_gestion(self.evento)
        res = self.client.patch(
            f"/api/gestiones/{gestion.id}/", {"horas": "9"}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.patch(
            f"/api/gestiones/{gestion.id}/", {"horas": "0.5"}, format="json"
        )
        self.assertEqual(res.status_code, 200)

    def test_crear_evento_valida_las_horas_de_su_plan(self):
        res = self.client.post(
            "/api/eventos/",
            {
                "nombre": "Fiesta",
                "fecha": "2026-12-20",
                "gestiones": [
                    {"nombre": "Sonido", "fecha": "2026-12-10", "hora": "10:00", "horas": "9"}
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class ReprogramarTests(BaseApiTestCase):
    def setUp(self):
        super().setUp()
        self.evento = self.crear_evento()  # límite 6 h
        self.mover = self.crear_gestion(
            self.evento, fecha="2026-10-10", horas="2", estado="pospuesto", nombre="Mover"
        )

    def url(self, gestion=None):
        return f"/api/gestiones/{(gestion or self.mover).id}/reprogramar/"

    def test_reprograma_dentro_del_limite(self):
        self.crear_gestion(self.evento, fecha="2026-10-12", horas="3")
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.mover.refresh_from_db()
        self.assertEqual(str(self.mover.fecha), "2026-10-12")
        self.assertEqual(self.mover.estado, "pendiente")  # reabre la gestión
        self.assertEqual(res.data["fecha"], "2026-10-12")

    def test_justo_en_el_limite_se_permite(self):
        self.crear_gestion(self.evento, fecha="2026-10-12", horas="4")  # 4 + 2 = 6
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_409_si_se_pasa_del_limite(self):
        existente = self.crear_gestion(
            self.evento, fecha="2026-10-12", horas="4.5", nombre="Catering"
        )
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 409)

        cuerpo = res.json()
        self.assertFalse(cuerpo["success"])
        self.assertEqual(cuerpo["error"]["status"], 409)
        self.assertTrue(cuerpo["error"]["message"])

        d = cuerpo["error"]["details"]
        self.assertEqual(d["fecha"], "2026-10-12")
        self.assertEqual(d["horas"], 6.5)    # 4.5 ya planeadas + 2 de la gestión
        self.assertEqual(d["limite"], 6.0)
        self.assertEqual(d["exceso"], 0.5)
        self.assertEqual([g["id"] for g in d["gestiones"]], [existente.id])
        self.assertEqual(d["gestiones"][0]["evento"]["nombre"], "Boda")

        # no se guardó nada
        self.mover.refresh_from_db()
        self.assertEqual(str(self.mover.fecha), "2026-10-10")
        self.assertEqual(self.mover.estado, "pospuesto")

    def test_las_hechas_no_cuentan(self):
        self.crear_gestion(self.evento, fecha="2026-10-12", horas="8", estado="hecho")
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_las_pospuestas_si_cuentan(self):
        self.crear_gestion(self.evento, fecha="2026-10-12", horas="5", estado="pospuesto")
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_cuentan_las_gestiones_de_otros_eventos_del_usuario(self):
        otro_evento = self.crear_evento(nombre="Bautizo")
        self.crear_gestion(otro_evento, fecha="2026-10-12", horas="5")
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_no_cuentan_las_gestiones_de_otros_usuarios(self):
        ajeno = self.crear_evento(usuario=self.otro, nombre="Ajeno")
        self.crear_gestion(ajeno, fecha="2026-10-12", horas="8")
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_la_gestion_no_se_cuenta_a_si_misma(self):
        self.mover.horas = Decimal("6")
        self.mover.save()
        res = self.client.post(self.url(), {"fecha": "2026-10-10"}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_usa_el_limite_global_del_usuario(self):
        preferencias = PreferenciasUsuario.de_usuario(self.user)
        preferencias.limite_horas = Decimal("3")
        preferencias.save()

        self.crear_gestion(
            self.evento,
            fecha="2026-10-12",
            horas="2",
        )

        res = self.client.post(
            self.url(),
            {"fecha": "2026-10-12"},
            format="json",
        )

        self.assertEqual(res.status_code, 409)
        self.assertEqual(
            res.json()["error"]["details"]["limite"],
            3.0,
        )


    def test_horas_nuevas_cuentan_para_el_limite(self):
        self.crear_gestion(self.evento, fecha="2026-10-12", horas="4")
        res = self.client.post(
            self.url(), {"fecha": "2026-10-12", "horas": "0.5"}, format="json"
        )
        self.assertEqual(res.status_code, 200)  # 4 + 0.5
        self.mover.refresh_from_db()
        self.assertEqual(self.mover.horas, Decimal("0.5"))

        otra = self.crear_gestion(self.evento, fecha="2026-10-11", horas="2")
        res = self.client.post(
            self.url(otra), {"fecha": "2026-10-12", "horas": "2"}, format="json"
        )
        self.assertEqual(res.status_code, 409)  # 4 + 0.5 + 2 = 6.5

    def test_puede_cambiar_la_hora(self):
        res = self.client.post(
            self.url(), {"fecha": "2026-10-15", "hora": "14:30"}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.mover.refresh_from_db()
        self.assertEqual(self.mover.hora.strftime("%H:%M"), "14:30")

    def test_fecha_obligatoria_e_invalida_dan_400(self):
        res = self.client.post(self.url(), {}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("fecha", res.data["error"]["details"])
        res = self.client.post(self.url(), {"fecha": "mañana"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_horas_fuera_de_rango_o_texto_dan_400(self):
        for valor in ("0.4", "8.5", "abc"):
            res = self.client.post(
                self.url(), {"fecha": "2026-10-15", "horas": valor}, format="json"
            )
            self.assertEqual(res.status_code, 400, valor)
            self.assertIn("horas", res.data["error"]["details"])

    def test_gestion_de_otro_usuario_da_404(self):
        ajeno = self.crear_evento(usuario=self.otro, nombre="Ajeno")
        g = self.crear_gestion(ajeno)
        res = self.client.post(self.url(g), {"fecha": "2026-10-15"}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_requiere_autenticacion(self):
        self.client.credentials()
        res = self.client.post(self.url(), {"fecha": "2026-10-15"}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_el_patch_generico_no_valida_el_limite(self):
        self.crear_gestion(self.evento, fecha="2026-10-12", horas="8")
        res = self.client.patch(
            f"/api/gestiones/{self.mover.id}/",
            {"fecha": "2026-10-12", "estado": "pendiente"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.mover.refresh_from_db()
        self.assertEqual(str(self.mover.fecha), "2026-10-12")


class EditarEventoAgregarGestionesTests(BaseApiTestCase):
    def setUp(self):
        super().setUp()
        self.evento = self.crear_evento()
        self.g1 = self.crear_gestion(self.evento, nombre="Catering", horas="2")
        self.url = f"/api/eventos/{self.evento.id}/"

    def nueva(self, **extra):
        data = {"nombre": "Fotógrafo", "fecha": "2026-10-20", "hora": "15:00", "horas": "3"}
        data.update(extra)
        return data

    def test_agrega_gestiones_nuevas_al_editar(self):
        res = self.client.patch(
            self.url,
            {"gestiones": [self.nueva(), self.nueva(nombre="DJ")]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.evento.gestiones.count(), 3)
        self.assertEqual(len(res.data["gestiones"]), 3)
        self.assertTrue(self.evento.gestiones.filter(nombre="DJ").exists())

    def test_mezcla_editar_existente_y_agregar_nueva(self):
        res = self.client.patch(
            self.url,
            {
                "nombre": "Boda de Ana",
                "gestiones": [
                    {"id": self.g1.id, "nombre": "Catering confirmado"},
                    self.nueva(),
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.evento.refresh_from_db()
        self.g1.refresh_from_db()
        self.assertEqual(self.evento.nombre, "Boda de Ana")
        self.assertEqual(self.g1.nombre, "Catering confirmado")
        self.assertEqual(self.g1.horas, Decimal("2"))  # lo no enviado no cambia
        self.assertEqual(self.evento.gestiones.count(), 2)

    def test_las_gestiones_no_mencionadas_no_se_borran(self):
        self.client.patch(self.url, {"gestiones": [self.nueva()]}, format="json")
        self.assertTrue(Gestion.objects.filter(pk=self.g1.pk).exists())

    def test_gestiones_vacias_en_patch_no_falla(self):
        res = self.client.patch(self.url, {"gestiones": []}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.evento.gestiones.count(), 1)

    def test_gestion_nueva_incompleta_da_400(self):
        res = self.client.patch(
            self.url, {"gestiones": [{"nombre": "Sin hora"}]}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.evento.gestiones.count(), 1)

    def test_gestion_nueva_valida_las_horas(self):
        res = self.client.patch(
            self.url, {"gestiones": [self.nueva(horas="9")]}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_id_de_otro_evento_da_400(self):
        otro = self.crear_evento(nombre="Otro")
        ajena = self.crear_gestion(otro, nombre="Ajena")
        res = self.client.patch(
            self.url,
            {"gestiones": [{"id": ajena.id, "nombre": "Robada"}]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        ajena.refresh_from_db()
        self.assertEqual(ajena.nombre, "Ajena")

    def test_si_algo_falla_no_se_guarda_nada(self):
        res = self.client.patch(
            self.url,
            {"nombre": "Nombre nuevo", "gestiones": [self.nueva(), {"nombre": "Incompleta"}]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.nombre, "Boda")
        self.assertEqual(self.evento.gestiones.count(), 1)

    def test_editar_solo_nombre_sigue_funcionando(self):
        res = self.client.patch(self.url, {"nombre": "Otro nombre"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.evento.gestiones.count(), 1)

    def test_no_se_puede_editar_evento_ajeno(self):
        self.autenticar(self.otro)
        res = self.client.patch(self.url, {"gestiones": [self.nueva()]}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_crear_evento_sigue_exigiendo_al_menos_una_gestion(self):
        res = self.client.post(
            "/api/eventos/",
            {"nombre": "Vacío", "fecha": "2026-12-20", "gestiones": []},
            format="json",
        )
        self.assertEqual(res.status_code, 400)