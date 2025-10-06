# -*- coding: utf-8 -*-
import os, time, sqlite3
from datetime import datetime, timezone
from jnius import autoclass, cast

# --- Utilidades Android (notificación foreground + canal) ---
def get_activity():
    PythonService = autoclass('org.kivy.android.PythonService')
    return PythonService.mService

def ensure_channel(activity, channel_id="rec_channel", channel_name="Recordatorios"):
    Build = autoclass('android.os.Build')
    if Build.VERSION.SDK_INT >= 26:
        NotificationChannel = autoclass('android.app.NotificationChannel')
        NotificationManager = autoclass('android.app.NotificationManager')
        Context = autoclass('android.content.Context')
        manager = cast(NotificationManager, activity.getSystemService(Context.NOTIFICATION_SERVICE))
        channel = NotificationChannel(channel_id, channel_name, NotificationManager.IMPORTANCE_DEFAULT)
        manager.createNotificationChannel(channel)

def foreground(activity, channel_id="rec_channel"):
    # Coloca el servicio en primer plano para que no lo mate el SO
    ensure_channel(activity, channel_id)
    Notification = autoclass('android.app.Notification')
    NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
    Context = autoclass('android.content.Context')
    builder = NotificationCompat.Builder(activity, channel_id)\
        .setContentTitle("Recordatorios activos")\
        .setContentText("Revisando recordatorios…")\
        .setSmallIcon(activity.getApplicationInfo().icon)
    notification = builder.build()
    activity.startForeground(1, notification)

def send_notification(activity, title, message, channel_id="rec_channel"):
    ensure_channel(activity, channel_id)
    NotificationManagerCompat = autoclass('androidx.core.app.NotificationManagerCompat')
    NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
    manager = NotificationManagerCompat.from(activity)
    builder = NotificationCompat.Builder(activity, channel_id)\
        .setContentTitle(title)\
        .setContentText(message)\
        .setSmallIcon(activity.getApplicationInfo().icon)\
        .setAutoCancel(True)\
        .setPriority(NotificationCompat.PRIORITY_HIGH)
    manager.notify(int(time.time() % 2_000_000_000), builder.build())

def get_db_path():
    base = os.environ.get('ANDROID_PRIVATE')
    if not base:
        # fallback; en p4a normalmente existe ANDROID_PRIVATE
        base = os.getcwd()
    return os.path.join(base, 'recordatorios.db')

def ensure_schema(db):
    cur = db.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS recordatorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        texto TEXT NOT NULL,
        minutos INTEGER,
        fecha_creado TEXT DEFAULT CURRENT_TIMESTAMP,
        activo INTEGER DEFAULT 1,
        notificado INTEGER DEFAULT 0
      );
    """)
    try:
        cur.execute("ALTER TABLE recordatorios ADD COLUMN notificado INTEGER DEFAULT 0;")
    except Exception:
        pass
    db.commit()

def parse_ts(ts):
    # SQLite CURRENT_TIMESTAMP -> 'YYYY-MM-DD HH:MM:SS'
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.utcnow().replace(tzinfo=timezone.utc)

def main():
    activity = get_activity()
    foreground(activity)  # convierte el servicio en Foreground Service

    db_path = get_db_path()
    db = sqlite3.connect(db_path, check_same_thread=False)
    ensure_schema(db)

    while True:
        try:
            cur = db.cursor()
            cur.execute("""
                SELECT id, texto, minutos, fecha_creado, notificado
                FROM recordatorios
                WHERE activo=1 AND minutos IS NOT NULL
            """)
            rows = cur.fetchall()
            now = datetime.utcnow().replace(tzinfo=timezone.utc)

            for rid, texto, minutos, fecha_creado, notificado in rows:
                if notificado:
                    continue
                base_time = parse_ts(fecha_creado)
                if minutos is not None and (now - base_time).total_seconds() >= minutos * 60:
                    send_notification(activity, "Recordatorio", texto)
                    cur.execute("UPDATE recordatorios SET notificado=1 WHERE id=?", (rid,))
                    db.commit()
        except Exception:
            # evita que el servicio muera por una excepción
            pass

        time.sleep(30)  # revisa cada 30s

if __name__ == '__main__':
    main()
