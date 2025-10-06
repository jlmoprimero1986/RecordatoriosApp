# -*- coding: utf-8 -*-
import os
import sqlite3
from datetime import datetime
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.core.window import Window

# Colores y tamaños pensados para adultos mayores
Window.clearcolor = (0.96, 0.97, 0.99, 1)  # fondo claro suave

try:
    from plyer import notification, vibrator
except Exception:
    notification = None
    vibrator = None


DB_PATH = "recordatorios.db"


def asegurar_permiso_notificaciones():
    # Pide POST_NOTIFICATIONS en Android 13+
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        ContextCompat = autoclass('androidx.core.content.ContextCompat')
        ActivityCompat = autoclass('androidx.core.app.ActivityCompat')
        Manifest = autoclass('android.Manifest')
        PackageManager = autoclass('android.content.pm.PackageManager')

        activity = PythonActivity.mActivity
        permission = Manifest.permission.POST_NOTIFICATIONS
        granted = (ContextCompat.checkSelfPermission(activity, permission) ==
                   PackageManager.PERMISSION_GRANTED)
        if not granted:
            ActivityCompat.requestPermissions(activity, [permission], 1001)
            return False
        return True
    except Exception:
        # En escritorio o si falla jnius, seguimos sin bloquear
        return True


def abrir_config_notificaciones():
    # Abre la pantalla de ajustes de notificaciones de la app (plan B)
    try:
        from jnius import autoclass
        Intent = autoclass('android.content.Intent')
        Settings = autoclass('android.provider.Settings')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity

        intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
        intent.putExtra('android.provider.extra.APP_PACKAGE', activity.getPackageName())
        activity.startActivity(intent)
    except Exception:
        pass


def solicitar_ignorar_ahorro_bateria():
    try:
        from jnius import autoclass
        Intent = autoclass('android.content.Intent')
        Settings = autoclass('android.provider.Settings')
        Uri = autoclass('android.net.Uri')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        pkg = activity.getPackageName()
        intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
        intent.setData(Uri.parse('package:' + pkg))
        activity.startActivity(intent)
    except Exception:
        pass


def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recordatorios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT NOT NULL,
            minutos INTEGER,               -- minutos relativos (opcional)
            fecha_creado TEXT DEFAULT CURRENT_TIMESTAMP,
            activo INTEGER DEFAULT 1,
            notificado INTEGER DEFAULT 0
        );
    """)
    # Garantiza columna 'notificado' si la tabla ya existía sin ella
    try:
        cur.execute("ALTER TABLE recordatorios ADD COLUMN notificado INTEGER DEFAULT 0;")
    except Exception:
        pass
    con.commit()
    con.close()


class AddRecordatorioPopup(Popup):
    def __init__(self, on_save, **kwargs):
        super().__init__(**kwargs)
        self.title = "Nuevo recordatorio"
        self.size_hint = (0.9, 0.6)

        root = BoxLayout(orientation="vertical", padding=16, spacing=12)

        self.txt = TextInput(
            hint_text="Escribe el recordatorio…",
            multiline=True,
            font_size=24,
            size_hint=(1, 0.6)
        )
        root.add_widget(self.txt)

        self.min_input = TextInput(
            hint_text="Minutos para avisar (opcional)",
            input_filter="int",
            font_size=22,
            size_hint=(1, 0.2)
        )
        root.add_widget(self.min_input)

        bar = BoxLayout(size_hint=(1, 0.2), spacing=12)
        btn_cancel = Button(text="Cancelar", font_size=22)
        btn_save = Button(text="Guardar", font_size=22)
        btn_cancel.bind(on_press=lambda *_: self.dismiss())
        btn_save.bind(on_press=lambda *_: self._guardar(on_save))
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_save)
        root.add_widget(bar)

        self.content = root

    def _guardar(self, on_save):
        texto = self.txt.text.strip()
        minutos = self.min_input.text.strip()
        minutos = int(minutos) if minutos.isdigit() else None
        if texto:
            on_save(texto, minutos)
            self.dismiss()


class RecordatorioItem(BoxLayout):
    def __init__(self, app, rid, texto, minutos, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.spacing = 10
        self.size_hint_y = None
        self.height = 64
        self.app = app
        self.rid = rid
        self.texto = texto
        self.minutos = minutos

        lbl = Label(
            text=texto,
            font_size=22,
            halign="left",
            valign="middle",
            shorten=True
        )
        lbl.bind(size=lambda *_: setattr(lbl, "text_size", lbl.size))

        btn_probar = Button(text="Probar 🔔", font_size=20)
        btn_probar.bind(on_press=lambda *_: self.app.enviar_notificacion(self.texto))

        btn_borrar = Button(text="Borrar", font_size=20)
        btn_borrar.bind(on_press=lambda *_: self.app.borrar_recordatorio(self.rid, self))

        self.add_widget(lbl)
        self.add_widget(btn_probar)
        self.add_widget(btn_borrar)


class RecordatoriosApp(App):
    def build(self):
        init_db()
        self.title = "Recordatorios Inteligentes"

        root = BoxLayout(orientation="vertical", padding=16, spacing=12)

        # Barra superior con botones grandes
        top = BoxLayout(size_hint=(1, 0.18), spacing=12)
        btn_nuevo = Button(
            text="➕ Agregar recordatorio",
            font_size=26
        )
        btn_nuevo.bind(on_press=lambda *_: self.abrir_popup_nuevo())
        btn_probar = Button(text="Probar notificación 🔔", font_size=26)
        btn_probar.bind(on_press=lambda *_: self.enviar_notificacion("Notificación de prueba"))
        btn_bateria = Button(text="Mejorar entregas 🔋", font_size=26)
        btn_bateria.bind(on_press=lambda *_: solicitar_ignorar_ahorro_bateria())
        top.add_widget(btn_nuevo)
        top.add_widget(btn_probar)
        top.add_widget(btn_bateria)

        root.add_widget(top)

        # Lista con scroll
        self.scroll = ScrollView(size_hint=(1, 0.82))
        self.lista_layout = GridLayout(cols=1, spacing=8, size_hint_y=None, padding=(0, 6))
        self.lista_layout.bind(minimum_height=self.lista_layout.setter('height'))
        self.scroll.add_widget(self.lista_layout)
        root.add_widget(self.scroll)

        self.cargar_recordatorios()
        return root

    # --- DB helpers ---
    def cargar_recordatorios(self):
        self.lista_layout.clear_widgets()
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, texto, minutos FROM recordatorios WHERE activo=1 ORDER BY id DESC")
        rows = cur.fetchall()
        con.close()

        for rid, texto, minutos in rows:
            item = RecordatorioItem(self, rid, texto, minutos)
            self.lista_layout.add_widget(item)

    def guardar_recordatorio(self, texto, minutos):
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("INSERT INTO recordatorios (texto, minutos) VALUES (?, ?)", (texto, minutos))
        rid = cur.lastrowid
        con.commit()
        con.close()

        # Añadir a la UI
        item = RecordatorioItem(self, rid, texto, minutos)
        self.lista_layout.add_widget(item, index=0)  # arriba

        # Programar alarma (mientras la app esté abierta)
        if isinstance(minutos, int) and minutos > 0:
            Clock.schedule_once(lambda dt: self.enviar_notificacion(texto), minutos * 60)

    def borrar_recordatorio(self, rid, widget):
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("UPDATE recordatorios SET activo=0 WHERE id=?", (rid,))
        con.commit()
        con.close()
        # Quitar de la UI
        self.lista_layout.remove_widget(widget)

    # --- UI actions ---
    def abrir_popup_nuevo(self):
        pop = AddRecordatorioPopup(on_save=self.guardar_recordatorio)
        pop.open()

    # --- Notificación y vibración ---
    def enviar_notificacion(self, mensaje):
        # Pedir permiso si hace falta
        if not asegurar_permiso_notificaciones():
            # Si el usuario niega, ofrecemos abrir ajustes
            self.mostrar_popup_permiso()
            return
        
        # Vibración suave si está disponible
        try:
            if vibrator and hasattr(vibrator, "vibrate"):
                vibrator.vibrate(0.5)
        except Exception:
            pass

        try:
            if notification:
                notification.notify(
                    title="Recordatorio",
                    message=mensaje,
                    app_name="Recordatorios Inteligentes",
                    timeout=10  # puede ser ignorado en Android
                )
        except Exception:
            pass

    def mostrar_popup_permiso(self):
        box = BoxLayout(orientation="vertical", padding=16, spacing=12)
        box.add_widget(Label(text="Para mostrar avisos, permite las notificaciones.", font_size=22))
        bar = BoxLayout(size_hint=(1, 0.3), spacing=12)
        btn_ajustes = Button(text="Abrir ajustes", font_size=22)
        btn_cerrar = Button(text="Cerrar", font_size=22)
        pop = Popup(title="Permiso requerido", content=box, size_hint=(0.9, 0.5))
        btn_ajustes.bind(on_press=lambda *_: (abrir_config_notificaciones(), pop.dismiss()))
        btn_cerrar.bind(on_press=lambda *_: pop.dismiss())
        bar.add_widget(btn_ajustes)
        bar.add_widget(btn_cerrar)
        box.add_widget(bar)
        pop.open()

    def on_start(self):
        # Iniciar el servicio solo una vez
        try:
            from android import AndroidService
            if not hasattr(self, "service_started") or not self.service_started:
                self.service = AndroidService('Recordatorios activos', 'Revisando recordatorios…')
                self.service.start('service started')
                self.service_started = True
        except Exception:
            self.service = None

    def on_stop(self):
        # No detener el servicio para que siga notificando en segundo plano
        pass


if __name__ == "__main__":
    RecordatoriosApp().run()
