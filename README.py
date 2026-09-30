import sqlite3
import bcrypt
import sys
import tkinter as tk
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

APP_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    executable_dir = Path(sys.executable).resolve().parent
    project_database = executable_dir.parent / "cuentas.db"
    APP_DIR = executable_dir.parent if project_database.exists() else executable_dir

conexion = sqlite3.connect(APP_DIR / "cuentas.db")
conexion.execute("PRAGMA foreign_keys = ON")
conexion.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY,
        correo TEXT UNIQUE NOT NULL,
        contrasena_hash BLOB NOT NULL
    )
""")
conexion.execute("""
    CREATE TABLE IF NOT EXISTS preferencias_financieras (
        usuario_id INTEGER PRIMARY KEY,
        moneda TEXT NOT NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
    )
""")
conexion.execute("""
    CREATE TABLE IF NOT EXISTS movimientos (
        id INTEGER PRIMARY KEY,
        usuario_id INTEGER NOT NULL,
        tipo TEXT NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
        descripcion TEXT NOT NULL,
        monto_centavos INTEGER NOT NULL CHECK (monto_centavos > 0),
        fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
    )
""")
columnas_movimientos = {
    fila[1] for fila in conexion.execute("PRAGMA table_info(movimientos)")
}
for nombre, definicion in (
    ("categoria", "TEXT NOT NULL DEFAULT 'Otros'"),
    ("metodo", "TEXT NOT NULL DEFAULT 'Efectivo'"),
    ("notas", "TEXT NOT NULL DEFAULT ''"),
):
    if nombre not in columnas_movimientos:
        conexion.execute(f"ALTER TABLE movimientos ADD COLUMN {nombre} {definicion}")
conexion.commit()


def formatear_dinero(centavos, moneda):
    importe = Decimal(centavos) / Decimal(100)
    return f"{importe:.2f} {moneda}"


class GestorFinanzasApp:
    etiqueta_saldo: tk.Label
    tabla: ttk.Treeview
    etiqueta_ingresos: tk.Label
    etiqueta_gastos: tk.Label
    grafica: tk.Canvas
    BACKGROUND = "#F2F5F0"
    INK = "#173D35"
    MUTED = "#65756E"
    ACCENT = "#237A64"
    WHITE = "#FFFFFF"
    BORDER = "#DCE5DD"

    def __init__(self, main_window):
        self.root = main_window
        self.usuario_id = None
        self.correo = None
        self.moneda = None
        self.root.title("Gestor de Finanzas")
        self.root.geometry("500x650")
        self.root.minsize(440, 600)
        self.root.configure(bg=self.BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar)

        style = ttk.Style(main_window)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=self.WHITE,
            fieldbackground=self.WHITE,
            foreground=self.INK,
            rowheight=34,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#E7EEE8",
            foreground=self.INK,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.configure("Treeview", borderwidth=0)
        self.mostrar_acceso()

    def limpiar_ventana(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def boton(self, parent, text, command, primary=True):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.ACCENT if primary else self.WHITE,
            fg=self.WHITE if primary else self.INK,
            activebackground="#195F4E" if primary else "#E7EEE8",
            activeforeground=self.WHITE if primary else self.INK,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bd=0,
            padx=18,
            pady=11,
            cursor="hand2",
        )

    def mostrar_acceso(self, modo="login"):
        self.limpiar_ventana()
        self.root.geometry("500x650")
        self.root.configure(bg=self.BACKGROUND)

        cabecera = tk.Frame(self.root, bg=self.INK, height=132)
        cabecera.pack(fill="x")
        cabecera.pack_propagate(False)
        tk.Label(
            cabecera,
            text="GESTOR DE FINANZAS",
            bg=self.INK,
            fg=self.WHITE,
            font=("Georgia", 20, "bold"),
        ).pack(anchor="w", padx=46, pady=(35, 4))
        tk.Label(
            cabecera,
            text="Control claro de tu dinero",
            bg=self.INK,
            fg="#C6D8CE",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=48)

        formulario = tk.Frame(self.root, bg=self.BACKGROUND)
        formulario.pack(fill="both", expand=True, padx=54, pady=(34, 30))
        titulo = "INICIAR SESION" if modo == "login" else "CREAR CUENTA"
        tk.Label(
            formulario,
            text=titulo,
            bg=self.BACKGROUND,
            fg=self.INK,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", pady=(0, 25))

        tk.Label(formulario, text="Correo", bg=self.BACKGROUND, fg=self.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 7))
        self.campo_correo = tk.Entry(
            formulario, font=("Segoe UI", 11), relief="solid", bd=1,
            highlightthickness=0,
        )
        self.campo_correo.pack(fill="x", ipady=10, pady=(0, 18))

        tk.Label(formulario, text="Contrasena", bg=self.BACKGROUND, fg=self.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 7))
        self.campo_contrasena = tk.Entry(
            formulario, show="*", font=("Segoe UI", 11), relief="solid", bd=1,
            highlightthickness=0,
        )
        self.campo_contrasena.pack(fill="x", ipady=10, pady=(0, 18))

        self.campo_confirmacion = None
        if modo == "registro":
            tk.Label(formulario, text="Repite la contrasena", bg=self.BACKGROUND,
                     fg=self.INK, font=("Segoe UI", 10, "bold")).pack(
                         anchor="w", pady=(0, 7))
            self.campo_confirmacion = tk.Entry(
                formulario, show="*", font=("Segoe UI", 11), relief="solid", bd=1,
                highlightthickness=0,
            )
            self.campo_confirmacion.pack(fill="x", ipady=10, pady=(0, 18))

        texto_boton = "INICIAR SESION" if modo == "login" else "CREAR CUENTA"
        self.boton(
            formulario,
            texto_boton,
            self.iniciar_sesion if modo == "login" else self.registrar,
        ).pack(fill="x", pady=(8, 16))

        cambiar = "Crear una cuenta" if modo == "login" else "Ya tengo una cuenta"
        tk.Button(
            formulario,
            text=cambiar,
            command=lambda: self.mostrar_acceso(
                "registro" if modo == "login" else "login"
            ),
            bg=self.BACKGROUND,
            fg=self.ACCENT,
            activebackground=self.BACKGROUND,
            activeforeground=self.INK,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
        ).pack()
        self.campo_correo.focus_set()
        self.campo_contrasena.bind(
            "<Return>", lambda _event: self.iniciar_sesion()
            if modo == "login" else self.registrar()
        )

    def iniciar_sesion(self):
        correo = self.campo_correo.get().strip().lower()
        contrasena = self.campo_contrasena.get()
        if not correo or not contrasena:
            messagebox.showerror("Datos incompletos", "Escribe tu correo y contrasena.",
                                 parent=self.root)
            return

        resultado = conexion.execute(
            "SELECT id, contrasena_hash FROM usuarios WHERE correo = ?",
            (correo,),
        ).fetchone()
        if not resultado or not bcrypt.checkpw(
            contrasena.encode("utf-8"), resultado[1]
        ):
            messagebox.showerror(
                "No se pudo iniciar sesion",
                "El correo o la contrasena no son correctos.",
                parent=self.root,
            )
            return
        self.abrir_cuenta(resultado[0], correo)

    def registrar(self):
        correo = self.campo_correo.get().strip().lower()
        contrasena = self.campo_contrasena.get()
        confirmacion = self.campo_confirmacion.get()
        if not correo or not contrasena:
            messagebox.showerror("Datos incompletos", "Completa todos los campos.",
                                 parent=self.root)
            return
        if contrasena != confirmacion:
            messagebox.showerror("Contrasenas distintas", "Las contrasenas no coinciden.",
                                 parent=self.root)
            return

        hash_seguro = bcrypt.hashpw(
            contrasena.encode("utf-8"), bcrypt.gensalt()
        )
        try:
            cursor = conexion.execute(
                "INSERT INTO usuarios (correo, contrasena_hash) VALUES (?, ?)",
                (correo, hash_seguro),
            )
            conexion.commit()
        except sqlite3.IntegrityError:
            messagebox.showerror(
                "Correo registrado", "Ya existe una cuenta con ese correo.",
                parent=self.root,
            )
            return
        self.abrir_cuenta(cursor.lastrowid, correo)

    def abrir_cuenta(self, usuario_id, correo):
        resultado = conexion.execute(
            "SELECT moneda FROM preferencias_financieras WHERE usuario_id = ?",
            (usuario_id,),
        ).fetchone()
        moneda = resultado[0] if resultado else None
        while not moneda:
            moneda = simpledialog.askstring(
                "Moneda", "Escribe el codigo de moneda de 3 letras (por ejemplo EUR):",
                parent=self.root,
            )
            if moneda is None:
                self.mostrar_acceso()
                return
            moneda = moneda.strip().upper()
            if len(moneda) != 3 or not moneda.isascii() or not moneda.isalpha():
                messagebox.showerror(
                    "Moneda no valida", "Usa un codigo de tres letras, como EUR o MXN.",
                    parent=self.root,
                )
                moneda = None
                continue
            conexion.execute(
                "INSERT INTO preferencias_financieras (usuario_id, moneda) VALUES (?, ?)",
                (usuario_id, moneda),
            )
            conexion.commit()

        self.usuario_id = usuario_id
        self.correo = correo
        self.moneda = moneda
        self.mostrar_panel()

    def mostrar_panel(self):
        self.limpiar_ventana()
        self.root.geometry("1080x790")
        self.root.minsize(820, 650)
        self.root.configure(bg=self.BACKGROUND)

        cabecera = tk.Frame(self.root, bg=self.INK, height=88)
        cabecera.pack(fill="x")
        cabecera.pack_propagate(False)
        tk.Label(cabecera, text="GESTOR DE FINANZAS", bg=self.INK, fg=self.WHITE,
                 font=("Georgia", 18, "bold")).pack(side="left", padx=32)
        tk.Label(cabecera, text=self.correo, bg=self.INK, fg="#C6D8CE",
                 font=("Segoe UI", 10)).pack(side="right", padx=16)
        tk.Button(
            cabecera, text="Cerrar sesion", command=self.cerrar_sesion,
            bg=self.INK, fg=self.WHITE, activebackground=self.INK,
            activeforeground="#C6D8CE", relief="flat", cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right", padx=(0, 28))

        contenido = tk.Frame(self.root, bg=self.BACKGROUND)
        contenido.pack(fill="both", expand=True, padx=32, pady=28)
        tk.Label(contenido, text="Tu panorama financiero", bg=self.BACKGROUND,
                 fg=self.INK, font=("Segoe UI", 21, "bold")).pack(
                     anchor="w", pady=(0, 16))

        indicadores = tk.Frame(contenido, bg=self.BACKGROUND)
        indicadores.pack(fill="x", pady=(0, 18))
        self.etiqueta_saldo = self.crear_indicador(
            indicadores, "SALDO TOTAL", self.INK, 0
        )
        self.etiqueta_ingresos = self.crear_indicador(
            indicadores, "INGRESOS DEL MES", self.ACCENT, 1
        )
        self.etiqueta_gastos = self.crear_indicador(
            indicadores, "GASTOS DEL MES", "#B65C4B", 2
        )

        visuales = tk.Frame(contenido, bg=self.WHITE,
                            highlightbackground=self.BORDER, highlightthickness=1)
        visuales.pack(fill="x", pady=(0, 18))
        tk.Label(visuales, text="Flujo de los ultimos 6 meses", bg=self.WHITE,
                 fg=self.INK, font=("Segoe UI", 11, "bold")).pack(
                     anchor="w", padx=18, pady=(12, 0))
        self.grafica = tk.Canvas(
            visuales, height=138, bg=self.WHITE, highlightthickness=0
        )
        self.grafica.pack(fill="x", padx=12, pady=(2, 10))
        self.grafica.bind("<Configure>", lambda _evento: self.dibujar_grafica())

        acciones = tk.Frame(contenido, bg=self.BACKGROUND)
        acciones.pack(fill="x", pady=(0, 18))
        self.boton(acciones, "+ Registrar ingreso",
                   lambda: self.nuevo_movimiento("ingreso")).pack(side="left")
        self.boton(acciones, "- Registrar gasto",
                   lambda: self.nuevo_movimiento("gasto"), primary=False).pack(
                       side="left", padx=10)
        tk.Label(contenido, text="Movimientos recientes", bg=self.BACKGROUND,
                 fg=self.INK, font=("Segoe UI", 13, "bold")).pack(
                     anchor="w", pady=(0, 9))

        tabla_marco = tk.Frame(contenido, bg=self.WHITE)
        tabla_marco.pack(fill="both", expand=True)
        columnas = ("fecha", "tipo", "categoria", "descripcion", "metodo", "importe")
        self.tabla = ttk.Treeview(
            tabla_marco, columns=columnas, show="headings", selectmode="browse"
        )
        self.tabla.tag_configure("ingreso", foreground=self.ACCENT)
        self.tabla.tag_configure("gasto", foreground="#B65C4B")
        self.tabla.bind("<Double-1>", self.ver_detalle_movimiento)
        encabezados = {
            "fecha": ("Fecha", 105),
            "tipo": ("Tipo", 82),
            "categoria": ("Categoria", 125),
            "descripcion": ("Descripcion", 220),
            "metodo": ("Metodo", 115),
            "importe": ("Importe", 135),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(columna, width=ancho, minwidth=80,
                              anchor="e" if columna == "importe" else "w",
                              stretch=columna == "descripcion")
        barra = ttk.Scrollbar(tabla_marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.actualizar_panel()

    def crear_indicador(self, parent, titulo, color, columna):
        tarjeta = tk.Frame(parent, bg=self.WHITE, highlightbackground=self.BORDER,
                           highlightthickness=1, padx=16, pady=13)
        tarjeta.grid(row=0, column=columna, sticky="nsew",
                     padx=(0 if columna == 0 else 7, 0 if columna == 2 else 7))
        parent.grid_columnconfigure(columna, weight=1, uniform="indicadores")
        tk.Label(tarjeta, text=titulo, bg=self.WHITE, fg=self.MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        valor = tk.Label(tarjeta, text="", bg=self.WHITE, fg=color,
                         font=("Segoe UI", 17, "bold"))
        valor.pack(anchor="w", pady=(5, 0))
        return valor

    def actualizar_panel(self):
        saldo = conexion.execute("""
            SELECT COALESCE(SUM(
                CASE WHEN tipo = 'ingreso' THEN monto_centavos ELSE -monto_centavos END
            ), 0)
            FROM movimientos
            WHERE usuario_id = ?
        """, (self.usuario_id,)).fetchone()[0]
        self.etiqueta_saldo.config(text=formatear_dinero(saldo, self.moneda))

        inicio_mes = date.today().replace(day=1).isoformat()
        totales_mes = conexion.execute("""
            SELECT tipo, COALESCE(SUM(monto_centavos), 0)
            FROM movimientos
            WHERE usuario_id = ? AND fecha >= ?
            GROUP BY tipo
        """, (self.usuario_id, inicio_mes)).fetchall()
        totales = dict(totales_mes)
        self.etiqueta_ingresos.config(
            text=formatear_dinero(totales.get("ingreso", 0), self.moneda)
        )
        self.etiqueta_gastos.config(
            text=formatear_dinero(totales.get("gasto", 0), self.moneda)
        )

        for item in self.tabla.get_children():
            self.tabla.delete(item)
        movimientos = conexion.execute("""
            SELECT id, fecha, tipo, categoria, descripcion, metodo, monto_centavos
            FROM movimientos
            WHERE usuario_id = ?
            ORDER BY id DESC
        """, (self.usuario_id,)).fetchall()
        for movimiento_id, fecha, tipo, categoria, descripcion, metodo, centavos in movimientos:
            signo = "+" if tipo == "ingreso" else "-"
            self.tabla.insert(
                "", "end", iid=str(movimiento_id), tags=(tipo,),
                values=(fecha[:10], tipo.capitalize(), categoria, descripcion, metodo,
                        f"{signo}{formatear_dinero(centavos, self.moneda)}"),
            )
        self.dibujar_grafica()

    def ver_detalle_movimiento(self, _evento=None):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        movimiento = conexion.execute("""
            SELECT fecha, tipo, descripcion, monto_centavos, categoria, metodo, notas
            FROM movimientos
            WHERE id = ? AND usuario_id = ?
        """, (int(seleccion[0]), self.usuario_id)).fetchone()
        if not movimiento:
            return
        fecha, tipo, descripcion, centavos, categoria, metodo, notas = movimiento
        detalle = tk.Toplevel(self.root)
        detalle.title("Detalle del movimiento")
        detalle.geometry("440x390")
        detalle.minsize(400, 350)
        detalle.configure(bg=self.BACKGROUND)
        detalle.transient(self.root)
        marco = tk.Frame(detalle, bg=self.WHITE, highlightbackground=self.BORDER,
                         highlightthickness=1, padx=24, pady=22)
        marco.pack(fill="both", expand=True, padx=22, pady=22)
        tk.Label(marco, text=descripcion, bg=self.WHITE, fg=self.INK,
                 font=("Segoe UI", 17, "bold"), wraplength=340,
                 justify="left").pack(anchor="w", pady=(0, 14))
        signo = "+" if tipo == "ingreso" else "-"
        tk.Label(marco, text=f"{signo}{formatear_dinero(centavos, self.moneda)}",
                 bg=self.WHITE, fg=self.ACCENT if tipo == "ingreso" else "#B65C4B",
                 font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(0, 15))
        for etiqueta, valor in (
            ("Fecha", fecha[:10]), ("Tipo", tipo.capitalize()),
            ("Categoria", categoria), ("Metodo de pago", metodo),
            ("Notas", notas or "Sin notas"),
        ):
            fila = tk.Frame(marco, bg=self.WHITE)
            fila.pack(fill="x", pady=3)
            tk.Label(fila, text=etiqueta, bg=self.WHITE, fg=self.MUTED,
                     font=("Segoe UI", 9, "bold"), width=16,
                     anchor="w").pack(side="left")
            tk.Label(fila, text=valor, bg=self.WHITE, fg=self.INK,
                     font=("Segoe UI", 10), wraplength=230,
                     justify="left").pack(side="left", fill="x", expand=True)

    def dibujar_grafica(self):
        if not hasattr(self, "grafica") or not self.grafica.winfo_exists():
            return
        canvas = self.grafica
        canvas.delete("all")
        ancho = max(canvas.winfo_width(), 360)
        alto = max(canvas.winfo_height(), 120)
        meses = []
        actual = date.today().replace(day=1)
        for desplazamiento in range(5, -1, -1):
            mes = actual.month - desplazamiento
            anio = actual.year
            while mes <= 0:
                mes += 12
                anio -= 1
            meses.append(date(anio, mes, 1))
        valores = conexion.execute("""
            SELECT substr(fecha, 1, 7), tipo, SUM(monto_centavos)
            FROM movimientos
            WHERE usuario_id = ? AND fecha >= ?
            GROUP BY substr(fecha, 1, 7), tipo
        """, (self.usuario_id, meses[0].strftime("%Y-%m"))).fetchall()
        datos = {(periodo, tipo): total for periodo, tipo, total in valores}
        maximo = max((total for total in datos.values()), default=0) or 1
        margen = 24
        base = alto - 28
        espacio = (ancho - margen * 2) / 6
        canvas.create_line(margen, base, ancho - margen, base, fill=self.BORDER)
        etiquetas = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul",
                     "Ago", "Sep", "Oct", "Nov", "Dic")
        for indice, mes in enumerate(meses):
            centro = margen + espacio * (indice + 0.5)
            for tipo, color, ajuste in (
                ("ingreso", self.ACCENT, -10), ("gasto", "#D88A72", 2)
            ):
                total = datos.get((mes.strftime("%Y-%m"), tipo), 0)
                altura = (total / maximo) * (alto - 57)
                canvas.create_rectangle(
                    centro + ajuste - 7, base - altura, centro + ajuste + 3, base,
                    fill=color, outline="",
                )
            canvas.create_text(
                centro, alto - 12, text=f"{etiquetas[mes.month - 1]} {str(mes.year)[-2:]}",
                fill=self.MUTED, font=("Segoe UI", 8),
            )

    def nuevo_movimiento(self, tipo):
        dialogo = tk.Toplevel(self.root)
        dialogo.title("Registrar " + tipo)
        dialogo.geometry("500x650")
        dialogo.minsize(460, 610)
        dialogo.configure(bg=self.BACKGROUND)
        dialogo.transient(self.root)
        dialogo.grab_set()

        contenido = tk.Frame(dialogo, bg=self.BACKGROUND, padx=30, pady=26)
        contenido.pack(fill="both", expand=True)
        tk.Label(contenido, text="REGISTRAR " + tipo.upper(), bg=self.BACKGROUND,
                 fg=self.INK, font=("Segoe UI", 14, "bold")).pack(
                     anchor="w", pady=(0, 20))
        tk.Label(contenido, text="Descripcion", bg=self.BACKGROUND, fg=self.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        campo_descripcion = tk.Entry(contenido, font=("Segoe UI", 11), relief="solid", bd=1)
        campo_descripcion.pack(fill="x", ipady=8, pady=(0, 15))
        tk.Label(contenido, text="Categoria", bg=self.BACKGROUND, fg=self.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        categorias = (
            "Vivienda", "Alimentacion", "Transporte", "Salud", "Educacion",
            "Ocio", "Servicios", "Salario", "Ventas", "Ahorro", "Otros",
        )
        categoria_var = tk.StringVar(value="Otros")
        ttk.Combobox(contenido, textvariable=categoria_var, values=categorias,
                     state="readonly", font=("Segoe UI", 10)).pack(
                         fill="x", ipady=5, pady=(0, 14))
        tk.Label(contenido, text=f"Importe ({self.moneda})", bg=self.BACKGROUND,
                 fg=self.INK, font=("Segoe UI", 10, "bold")).pack(
                     anchor="w", pady=(0, 6))
        campo_importe = tk.Entry(contenido, font=("Segoe UI", 11), relief="solid", bd=1)
        campo_importe.pack(fill="x", ipady=8, pady=(0, 14))
        fila_extra = tk.Frame(contenido, bg=self.BACKGROUND)
        fila_extra.pack(fill="x", pady=(0, 14))
        bloque_fecha = tk.Frame(fila_extra, bg=self.BACKGROUND)
        bloque_fecha.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(bloque_fecha, text="Fecha (AAAA-MM-DD)", bg=self.BACKGROUND,
                 fg=self.INK, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))
        campo_fecha = tk.Entry(bloque_fecha, font=("Segoe UI", 10), relief="solid", bd=1)
        campo_fecha.insert(0, date.today().isoformat())
        campo_fecha.pack(fill="x", ipady=7)
        bloque_metodo = tk.Frame(fila_extra, bg=self.BACKGROUND)
        bloque_metodo.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(bloque_metodo, text="Metodo de pago", bg=self.BACKGROUND,
                 fg=self.INK, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))
        metodo_var = tk.StringVar(value="Efectivo")
        ttk.Combobox(
            bloque_metodo, textvariable=metodo_var,
            values=("Efectivo", "Tarjeta", "Transferencia", "Domiciliacion", "Otro"),
            state="readonly", font=("Segoe UI", 10),
        ).pack(fill="x", ipady=5)
        tk.Label(contenido, text="Notas (opcional)", bg=self.BACKGROUND, fg=self.INK,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))
        campo_notas = tk.Text(contenido, height=3, font=("Segoe UI", 10),
                              relief="solid", bd=1, wrap="word")
        campo_notas.pack(fill="x", pady=(0, 14))

        def guardar():
            descripcion = campo_descripcion.get().strip()
            if not descripcion:
                messagebox.showerror("Falta la descripcion", "Escribe una descripcion.",
                                     parent=dialogo)
                return
            try:
                fecha_movimiento = datetime.strptime(
                    campo_fecha.get().strip(), "%Y-%m-%d"
                ).date().isoformat()
            except ValueError:
                messagebox.showerror(
                    "Fecha no valida", "Usa una fecha valida con formato AAAA-MM-DD.",
                    parent=dialogo,
                )
                return
            try:
                importe = Decimal(campo_importe.get().strip().replace(",", "."))
            except InvalidOperation:
                messagebox.showerror("Importe no valido", "Escribe un importe valido.",
                                     parent=dialogo)
                return
            if not importe.is_finite() or importe <= 0:
                messagebox.showerror("Importe no valido", "El importe debe ser mayor que cero.",
                                     parent=dialogo)
                return
            centavos = importe * 100
            if centavos != centavos.to_integral_value():
                messagebox.showerror("Importe no valido", "Usa como maximo dos decimales.",
                                     parent=dialogo)
                return
            conexion.execute(
                "INSERT INTO movimientos "
                "(usuario_id, tipo, descripcion, monto_centavos, fecha, categoria, metodo, notas) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.usuario_id, tipo, descripcion, int(centavos), fecha_movimiento,
                    categoria_var.get(), metodo_var.get(),
                    campo_notas.get("1.0", "end-1c").strip(),
                ),
            )
            conexion.commit()
            dialogo.destroy()
            self.actualizar_panel()

        self.boton(contenido, "GUARDAR MOVIMIENTO", guardar).pack(fill="x")
        campo_descripcion.focus_set()
        campo_importe.bind("<Return>", lambda _event: guardar())

    def cerrar_sesion(self):
        self.usuario_id = None
        self.correo = None
        self.moneda = None
        self.mostrar_acceso()

    def cerrar(self):
        conexion.close()
        self.root.destroy()


if __name__ == "__main__":
    app_root = tk.Tk()
    aplicacion = GestorFinanzasApp(app_root)
    app_root.mainloop()