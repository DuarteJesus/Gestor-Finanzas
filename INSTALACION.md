# Gestor de Finanzas para Windows y Android

La aplicacion instalada se ejecuta de forma nativa. El servidor solo sincroniza los datos; no presenta una interfaz web.

## Probar en un PC

En PowerShell, desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:JWT_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

En otra terminal, inicia la aplicacion de escritorio:

```powershell
python main.py
```

En la pantalla de acceso, la direccion local predeterminada es `http://127.0.0.1:8000`.

## Importar las cuentas existentes

Antes de iniciar el servidor por primera vez, conserva una copia de `cuentas.db` y ejecuta:

```powershell
python migrar_sqlite.py cuentas.db
```

Se copian cuentas, hashes de contrasena, monedas y movimientos. El importador se cancela si el destino ya contiene cuentas. Ejecutalo en el servidor o copia despues el archivo `gestor_finanzas_server.db` a su almacenamiento persistente.

## Usar en varios dispositivos

El servidor debe seguir encendido y ser accesible desde los dispositivos. Para probar en la misma red Wi-Fi, en el movil configura la direccion LAN del PC, por ejemplo `http://192.168.1.20:8000`, y permite el puerto 8000 en el firewall. En Internet, despliega la API con HTTPS y un volumen persistente, y configura esa URL HTTPS en la aplicacion de cada dispositivo. No publiques el servidor con HTTP sin cifrar.

El archivo SQLite central debe residir en almacenamiento persistente del servidor. Las bases guardadas dentro del contenedor sin volumen pueden desaparecer al recrearlo.

## Crear instaladores

Para crear el ejecutable Windows:

```powershell
python -m pip install -r requirements.txt
flet pack main.py --name GestorFinanzas --distpath dist_native
```

El resultado queda en `dist_native`. Para generar un APK Android se necesita Flutter, Java y Android SDK configurados:

```powershell
flet build apk --project gestor_finanzas --org com.gestor.finanzas --product "Gestor Finanzas" .
```

El APK queda dentro de `build\apk`. Para distribuir por Google Play se usa un AAB firmado. La compilacion de iPhone requiere macOS y Xcode.

## Variables del servidor

- `JWT_SECRET`: clave aleatoria larga; genera una exclusiva para produccion y no la incluyas en la app.
- `DATABASE_URL`: ruta persistente SQLite. En Docker ya apunta a `/data/gestor_finanzas_server.db`.

El Dockerfile de este proyecto expone la API en el puerto 8000. Configura `JWT_SECRET` y monta almacenamiento persistente en `/data` al desplegarlo. El proveedor debe ofrecer HTTPS.
