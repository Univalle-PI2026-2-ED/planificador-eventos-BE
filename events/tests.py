from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from django.utils import timezone

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

    def test_acepta_los_extremos_1_y_16(self):
        for valor in ("1", "16"):
            res = self.client.patch(self.url, {"limite_horas": valor}, format="json")
            self.assertEqual(res.status_code, 200, valor)

    def test_rechaza_limite_fuera_de_1_a_16(self):
        for valor in ("0", "0.5", "16.5", "17", "-3"):
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

    def test_acepta_de_0_5_a_16(self):
        for valor in ("0.5", "4", "16"):
            self.assertEqual(self.nueva(valor).status_code, 201, valor)

    def test_rechaza_fuera_de_0_5_a_16(self):
        for valor in ("0", "0.25", "0.4", "16.5", "17", "-1"):
            res = self.nueva(valor)
            self.assertEqual(res.status_code, 400, valor)
            self.assertIn("horas", res.data["error"]["details"])

    def test_patch_de_horas_tambien_valida(self):
        gestion = self.crear_gestion(self.evento)
        res = self.client.patch(
            f"/api/gestiones/{gestion.id}/", {"horas": "17"}, format="json"
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
                    {"nombre": "Sonido", "fecha": "2026-12-10", "hora": "10:00", "horas": "17"}
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

    def test_las_pospuestas_no_cuentan(self):
        # US-08: posponer retira la gestión del cálculo de horas del día
        self.crear_gestion(self.evento, fecha="2026-10-12", horas="5", estado="pospuesto")
        res = self.client.post(self.url(), {"fecha": "2026-10-12"}, format="json")
        self.assertEqual(res.status_code, 200)

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
        for valor in ("0.4", "16.5", "abc"):
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
            self.url, {"gestiones": [self.nueva(horas="17")]}, format="json"
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

    
    def test_reabrir_gestion_desde_evento_borra_fecha_cierre(self):
        self.g1.estado = "hecho"
        self.g1.fecha_cierre = timezone.now()
        self.g1.save()

        res = self.client.patch(
            self.url,
            {
                "gestiones": [
                    {"id": self.g1.id, "estado": "pendiente"}
                ]
            },
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.g1.refresh_from_db()
        self.assertEqual(self.g1.estado, "pendiente")
        self.assertIsNone(self.g1.fecha_cierre)




class FechaCierreGestionTests(BaseApiTestCase):
    def setUp(self):
        super().setUp()
        self.evento = self.crear_evento()
        self.gestion = self.crear_gestion(self.evento)
        self.url = f"/api/gestiones/{self.gestion.id}/"

    def test_al_marcar_hecha_se_guarda_fecha_cierre(self):
        antes = timezone.now()

        res = self.client.patch(
            self.url,
            {"estado": "hecho"},
            format="json",
        )

        despues = timezone.now()

        self.assertEqual(res.status_code, 200)
        self.gestion.refresh_from_db()
        self.assertIsNotNone(self.gestion.fecha_cierre)
        self.assertGreaterEqual(self.gestion.fecha_cierre, antes)
        self.assertLessEqual(self.gestion.fecha_cierre, despues)
        self.assertIsNotNone(res.data["fecha_cierre"])

    def test_al_reabrir_una_gestion_se_borra_fecha_cierre(self):
        self.gestion.estado = "hecho"
        self.gestion.fecha_cierre = timezone.now()
        self.gestion.save()

        res = self.client.patch(
            self.url,
            {"estado": "pendiente"},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.gestion.refresh_from_db()
        self.assertEqual(self.gestion.estado, "pendiente")
        self.assertIsNone(self.gestion.fecha_cierre)
        self.assertIsNone(res.data["fecha_cierre"])

    def test_al_posponer_una_gestion_hecha_se_borra_fecha_cierre(self):
        self.gestion.estado = "hecho"
        self.gestion.fecha_cierre = timezone.now()
        self.gestion.save()

        res = self.client.patch(
            self.url,
            {"estado": "pospuesto"},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.gestion.refresh_from_db()
        self.assertEqual(self.gestion.estado, "pospuesto")
        self.assertIsNone(self.gestion.fecha_cierre)

    def test_editar_nota_de_gestion_hecha_conserva_fecha_cierre(self):
        fecha_original = timezone.now()
        self.gestion.estado = "hecho"
        self.gestion.fecha_cierre = fecha_original
        self.gestion.save()

        res = self.client.patch(
            self.url,
            {"nota": "Confirmación recibida"},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.gestion.refresh_from_db()
        self.assertEqual(self.gestion.nota, "Confirmación recibida")
        self.assertEqual(self.gestion.fecha_cierre, fecha_original)

    def test_fecha_cierre_no_se_puede_asignar_desde_el_cliente(self):
        res = self.client.patch(
            self.url,
            {
                "estado": "pendiente",
                "fecha_cierre": "2026-10-13T12:00:00Z",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.gestion.refresh_from_db()
        self.assertIsNone(self.gestion.fecha_cierre)

    def test_nota_se_conserva_al_cambiar_estado(self):
        self.gestion.nota = "Esperando confirmación"
        self.gestion.save()

        res = self.client.patch(
            self.url,
            {"estado": "hecho"},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.gestion.refresh_from_db()
        self.assertEqual(self.gestion.nota, "Esperando confirmación")
        self.assertIsNotNone(self.gestion.fecha_cierre)



class ProgresoEventoTests(BaseApiTestCase):
    def setUp(self):
        super().setUp()
        self.evento = self.crear_evento()

    def test_progreso_con_gestiones_hechas_pendientes_y_pospuestas(self):
        self.crear_gestion(self.evento, estado="hecho", nombre="Hecha 1")
        self.crear_gestion(self.evento, estado="hecho", nombre="Hecha 2")
        self.crear_gestion(self.evento, estado="pendiente", nombre="Pendiente")
        self.crear_gestion(self.evento, estado="pospuesto", nombre="Pospuesta")

        res = self.client.get(f"/api/eventos/{self.evento.id}/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["gestiones_hechas"], 2)
        self.assertEqual(res.data["total_gestiones"], 4)
        self.assertEqual(res.data["progreso_porcentaje"], 50.0)

    def test_evento_sin_gestiones_tiene_progreso_cero(self):
        self.evento.gestiones.all().delete()

        res = self.client.get(f"/api/eventos/{self.evento.id}/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["gestiones_hechas"], 0)
        self.assertEqual(res.data["total_gestiones"], 0)
        self.assertEqual(res.data["progreso_porcentaje"], 0)

    def test_el_listado_tambien_incluye_el_progreso(self):
        self.crear_gestion(self.evento, estado="hecho")
        self.crear_gestion(self.evento, estado="pendiente")

        res = self.client.get("/api/eventos/")

        self.assertEqual(res.status_code, 200)

        # El endpoint de listado devuelve una lista de eventos.
        evento_data = next(
            item for item in res.data if item["id"] == self.evento.id
        )

        self.assertEqual(evento_data["gestiones_hechas"], 1)
        self.assertEqual(evento_data["total_gestiones"], 2)
        self.assertEqual(evento_data["progreso_porcentaje"], 50.0)



class ValidacionEstadoYHoyTests(BaseApiTestCase):
    def setUp(self):
        super().setUp()
        self.evento = self.crear_evento()

    def test_estado_invalido_devuelve_400_con_error_claro(self):
        gestion = self.crear_gestion(self.evento)

        res = self.client.patch(
            f"/api/gestiones/{gestion.id}/",
            {"estado": "en_proceso"},
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        detalles = res.data["error"]["details"]
        self.assertIn("estado", detalles)

    def test_gestion_inexistente_devuelve_404(self):
        res = self.client.patch(
            "/api/gestiones/999999/",
            {"estado": "hecho"},
            format="json",
        )

        self.assertEqual(res.status_code, 404)

    def test_gestion_de_otro_usuario_devuelve_404(self):
        evento_ajeno = self.crear_evento(
            usuario=self.otro,
            nombre="Evento ajeno",
        )
        gestion_ajena = self.crear_gestion(evento_ajeno)

        res = self.client.patch(
            f"/api/gestiones/{gestion_ajena.id}/",
            {"estado": "hecho"},
            format="json",
        )

        self.assertEqual(res.status_code, 404)

    def test_hoy_no_incluye_gestiones_hechas_en_pendientes(self):
        fecha_hoy = timezone.localdate().isoformat()

        hecha = self.crear_gestion(
            self.evento,
            fecha=fecha_hoy,
            estado="hecho",
            nombre="Gestión terminada",
        )
        pendiente = self.crear_gestion(
            self.evento,
            fecha=fecha_hoy,
            estado="pendiente",
            nombre="Gestión pendiente",
            hora="10:00",
        )

        res = self.client.get("/api/hoy/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["filtros"]["estado"], "pendiente")

        grupos = res.data["grupos"]
        ids_devueltos = {
            gestion["id"]
            for grupo in grupos.values()
            for gestion in grupo
        }

        self.assertIn(pendiente.id, ids_devueltos)
        self.assertNotIn(hecha.id, ids_devueltos)