import os
import sqlite3
import sys
import tkinter as tk
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import messagebox, ttk
from typing import cast

import bcrypt


def obtener_ruta_base():
    ruta_pruebas = os.environ.get("GESTOR_FINANZAS_DATA_DIR")
    if ruta_pruebas:
        carpeta_datos = Path(ruta_pruebas)
    else:
        carpeta_local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        carpeta_datos = carpeta_local / "GestorFinanzas"

    carpeta_datos.mkdir(parents=True, exist_ok=True)
    ruta_base = carpeta_datos / "cuentas.db"

    if not ruta_base.exists() and not ruta_pruebas:
        if getattr(sys, "frozen", False):
            carpeta_ejecutable = Path(sys.executable).resolve().parent
            bases_anteriores = (
                carpeta_ejecutable / "cuentas.db",
                carpeta_ejecutable.parent / "cuentas.db"
            )
        else:
            bases_anteriores = (Path(__file__).resolve().parent / "cuentas.db",)
        for base_anterior in bases_anteriores:
            if base_anterior.exists() and base_anterior.resolve() != ruta_base.resolve():
                origen = sqlite3.connect(base_anterior)
                destino = sqlite3.connect(ruta_base)
                origen.backup(destino)
                destino.close()
                origen.close()
                break

    return ruta_base


conexion = sqlite3.connect(obtener_ruta_base())
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
conexion.commit()


class GestorFinanzas:
    MONEDAS = ("EUR", "USD", "MXN", "COP", "ARS", "CLP", "PEN", "GBP")
    pestanas: ttk.Notebook
    resumen_tab: ttk.Frame
    nuevo_tab: ttk.Frame
    historial_tab: ttk.Frame
    cuenta_tab: ttk.Frame
    metricas: dict[str, ttk.Label]
    tipo_var: tk.StringVar
    descripcion_var: tk.StringVar
    importe_var: tk.StringVar
    moneda_form_label: ttk.Label
    tabla: ttk.Treeview
    moneda_var: tk.StringVar
    selector_moneda: ttk.Combobox
    boton_moneda: ttk.Button
    estado_moneda: ttk.Label

    def __init__(self, ventana):
        self.ventana = ventana
        self.usuario_id = None
        self.correo = ""
        self.moneda = None
        self.pestanas = cast(ttk.Notebook, None)
        self.resumen_tab = cast(ttk.Frame, None)
        self.nuevo_tab = cast(ttk.Frame, None)
        self.historial_tab = cast(ttk.Frame, None)
        self.cuenta_tab = cast(ttk.Frame, None)
        self.metricas = {}
        self.tipo_var = cast(tk.StringVar, None)
        self.descripcion_var = cast(tk.StringVar, None)
        self.importe_var = cast(tk.StringVar, None)
        self.moneda_form_label = cast(ttk.Label, None)
        self.tabla = cast(ttk.Treeview, None)
        self.moneda_var = cast(tk.StringVar, None)
        self.selector_moneda = cast(ttk.Combobox, None)
        self.boton_moneda = cast(ttk.Button, None)
        self.estado_moneda = cast(ttk.Label, None)

        self.ventana.title("Gestor de finanzas")
        self.ventana.geometry("940x640")
        self.ventana.minsize(760, 520)
        self.ventana.protocol("WM_DELETE_WINDOW", self.cerrar)

        estilo = ttk.Style()
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure("TFrame", background="#f4f6f5")
        estilo.configure("TLabel", background="#f4f6f5", font=("Segoe UI", 10))
        estilo.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        estilo.configure("Metric.TLabel", font=("Segoe UI", 18, "bold"))
        estilo.configure("TButton", padding=(12, 8))

        self.mostrar_acceso()

    def limpiar_ventana(self):
        for widget in self.ventana.winfo_children():
            widget.destroy()

    def mostrar_acceso(self):
        self.limpiar_ventana()
        marco = ttk.Frame(self.ventana, padding=36)
        marco.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(marco, text="Gestor de finanzas", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Label(marco, text="Inicia sesión o crea una cuenta para continuar.").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 20)
        )

        ttk.Label(marco, text="Correo").grid(row=2, column=0, columnspan=2, sticky="w")
        self.entrada_correo = ttk.Entry(marco, width=38)
        self.entrada_correo.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 14))

        ttk.Label(marco, text="Contraseña").grid(row=4, column=0, columnspan=2, sticky="w")
        self.entrada_contrasena = ttk.Entry(marco, width=38, show="*")
        self.entrada_contrasena.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 20))
        self.entrada_contrasena.bind("<Return>", lambda _evento: self.iniciar_sesion())

        ttk.Button(marco, text="Iniciar sesión", command=self.iniciar_sesion).grid(
            row=6, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(marco, text="Crear cuenta", command=self.registrar).grid(
            row=6, column=1, sticky="ew", padx=(6, 0)
        )
        self.entrada_correo.focus_set()

    def registrar(self):
        correo = self.entrada_correo.get().strip().lower()
        contrasena = self.entrada_contrasena.get()
        if "@" not in correo or "." not in correo.rsplit("@", 1)[-1]:
            messagebox.showerror("Correo no válido", "Escribe un correo válido.")
            return
        if len(contrasena) < 8:
            messagebox.showerror(
                "Contraseña corta", "La contraseña debe tener al menos 8 caracteres."
            )
            return

        hash_seguro = bcrypt.hashpw(contrasena.encode("utf-8"), bcrypt.gensalt())
        try:
            cursor = conexion.execute(
                "INSERT INTO usuarios (correo, contrasena_hash) VALUES (?, ?)",
                (correo, hash_seguro)
            )
            conexion.commit()
        except sqlite3.IntegrityError:
            messagebox.showerror("Cuenta existente", "Ese correo ya está registrado.")
            return

        self.abrir_finanzas(cursor.lastrowid, correo)

    def iniciar_sesion(self):
        correo = self.entrada_correo.get().strip().lower()
        contrasena = self.entrada_contrasena.get()
        usuario = conexion.execute(
            "SELECT id, contrasena_hash FROM usuarios WHERE correo = ?",
            (correo,)
        ).fetchone()

        if not usuario or not bcrypt.checkpw(contrasena.encode("utf-8"), usuario[1]):
            messagebox.showerror("Acceso denegado", "Correo o contraseña incorrectos.")
            return
        self.abrir_finanzas(usuario[0], correo)

    def abrir_finanzas(self, usuario_id, correo):
        self.usuario_id = usuario_id
        self.correo = correo
        preferencia = conexion.execute(
            "SELECT moneda FROM preferencias_financieras WHERE usuario_id = ?",
            (usuario_id,)
        ).fetchone()
        self.moneda = preferencia[0] if preferencia else None
        self.construir_panel()

    def construir_panel(self):
        self.limpiar_ventana()
        principal = ttk.Frame(self.ventana, padding=(24, 18))
        principal.pack(fill="both", expand=True)

        encabezado = ttk.Frame(principal)
        encabezado.pack(fill="x", pady=(0, 16))
        ttk.Label(encabezado, text="Finanzas", style="Title.TLabel").pack(side="left")
        ttk.Label(encabezado, text=self.correo).pack(side="right", padx=(12, 0))
        ttk.Button(encabezado, text="Cerrar sesión", command=self.mostrar_acceso).pack(side="right")

        self.pestanas = ttk.Notebook(principal)
        self.pestanas.pack(fill="both", expand=True)
        self.resumen_tab = ttk.Frame(self.pestanas, padding=22)
        self.nuevo_tab = ttk.Frame(self.pestanas, padding=22)
        self.historial_tab = ttk.Frame(self.pestanas, padding=18)
        self.cuenta_tab = ttk.Frame(self.pestanas, padding=22)
        self.pestanas.add(self.resumen_tab, text="Resumen")
        self.pestanas.add(self.nuevo_tab, text="Nuevo movimiento")
        self.pestanas.add(self.historial_tab, text="Historial")
        self.pestanas.add(self.cuenta_tab, text="Cuenta")
        self.pestanas.bind("<<NotebookTabChanged>>", self.actualizar_pestana)

        self.construir_resumen()
        self.construir_formulario()
        self.construir_historial()
        self.construir_cuenta()
        self.actualizar_resumen()
        self.actualizar_historial()

        if self.moneda is None:
            self.pestanas.select(self.cuenta_tab)

    def construir_resumen(self):
        ttk.Label(self.resumen_tab, text="Resumen", style="Title.TLabel").pack(anchor="w")
        fila = ttk.Frame(self.resumen_tab)
        fila.pack(fill="x", pady=(28, 0))
        self.metricas = {}
        for indice, (clave, titulo) in enumerate((
            ("saldo", "Saldo"), ("ingresos", "Ingresos"), ("gastos", "Gastos")
        )):
            bloque = ttk.LabelFrame(fila, text=titulo, padding=18)
            bloque.grid(row=0, column=indice, sticky="nsew", padx=(0, 12))
            self.metricas[clave] = ttk.Label(bloque, text="-", style="Metric.TLabel")
            self.metricas[clave].pack(anchor="w")
            fila.columnconfigure(indice, weight=1)

    def construir_formulario(self):
        ttk.Label(self.nuevo_tab, text="Registrar movimiento", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 22)
        )
        ttk.Label(self.nuevo_tab, text="Tipo").grid(row=1, column=0, sticky="w", pady=6)
        self.tipo_var = tk.StringVar(value="Gasto")
        ttk.Combobox(
            self.nuevo_tab, textvariable=self.tipo_var,
            values=("Ingreso", "Gasto"), state="readonly", width=30
        ).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(self.nuevo_tab, text="Descripción").grid(row=2, column=0, sticky="w", pady=6)
        self.descripcion_var = tk.StringVar()
        ttk.Entry(self.nuevo_tab, textvariable=self.descripcion_var, width=34).grid(
            row=2, column=1, sticky="ew", pady=6
        )

        ttk.Label(self.nuevo_tab, text="Importe").grid(row=3, column=0, sticky="w", pady=6)
        self.importe_var = tk.StringVar()
        ttk.Entry(self.nuevo_tab, textvariable=self.importe_var, width=34).grid(
            row=3, column=1, sticky="ew", pady=6
        )
        self.moneda_form_label = ttk.Label(self.nuevo_tab, text="")
        self.moneda_form_label.grid(row=4, column=1, sticky="w")
        ttk.Button(self.nuevo_tab, text="Guardar movimiento", command=self.guardar_movimiento).grid(
            row=5, column=1, sticky="w", pady=(18, 0)
        )
        self.nuevo_tab.columnconfigure(1, weight=1)
        self.actualizar_etiqueta_moneda()

    def construir_historial(self):
        ttk.Label(self.historial_tab, text="Movimientos", style="Title.TLabel").pack(
            anchor="w", pady=(0, 16)
        )
        columnas = ("fecha", "tipo", "descripcion", "importe")
        self.tabla = ttk.Treeview(self.historial_tab, columns=columnas, show="headings")
        for columna, titulo, ancho in (
            ("fecha", "Fecha", 160), ("tipo", "Tipo", 100),
            ("descripcion", "Descripción", 300), ("importe", "Importe", 130)
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="w")
        barra = ttk.Scrollbar(self.historial_tab, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

    def construir_cuenta(self):
        ttk.Label(self.cuenta_tab, text="Cuenta", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 22)
        )
        ttk.Label(self.cuenta_tab, text="Correo").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Label(self.cuenta_tab, text=self.correo).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(self.cuenta_tab, text="Moneda").grid(row=2, column=0, sticky="w", pady=6)
        self.moneda_var = tk.StringVar(value=self.moneda or "")
        self.selector_moneda = ttk.Combobox(
            self.cuenta_tab, textvariable=self.moneda_var,
            values=self.MONEDAS, state="readonly", width=12
        )
        self.selector_moneda.grid(row=2, column=1, sticky="w", pady=6)
        self.boton_moneda = ttk.Button(
            self.cuenta_tab, text="Guardar moneda", command=self.guardar_moneda
        )
        self.boton_moneda.grid(row=3, column=1, sticky="w", pady=(12, 0))
        self.estado_moneda = ttk.Label(self.cuenta_tab, text="")
        self.estado_moneda.grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.actualizar_estado_moneda()

    def actualizar_pestana(self, _evento=None):
        seleccion = self.pestanas.select()
        if seleccion == str(self.resumen_tab):
            self.actualizar_resumen()
        elif seleccion == str(self.historial_tab):
            self.actualizar_historial()

    def dinero(self, centavos):
        return f"{Decimal(centavos) / Decimal(100):.2f} {self.moneda or ''}".strip()

    def obtener_totales(self):
        return conexion.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto_centavos ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN tipo = 'gasto' THEN monto_centavos ELSE 0 END), 0)
            FROM movimientos
            WHERE usuario_id = ?
        """, (self.usuario_id,)).fetchone()

    def actualizar_resumen(self):
        ingresos, gastos = self.obtener_totales()
        if self.moneda is None:
            for etiqueta in self.metricas.values():
                etiqueta.configure(text="Elige moneda en Cuenta")
            return
        self.metricas["saldo"].configure(text=self.dinero(ingresos - gastos))
        self.metricas["ingresos"].configure(text=self.dinero(ingresos))
        self.metricas["gastos"].configure(text=self.dinero(gastos))

    def guardar_movimiento(self):
        if self.moneda is None:
            messagebox.showwarning("Falta la moneda", "Elige una moneda en la sección Cuenta.")
            self.pestanas.select(self.cuenta_tab)
            return

        descripcion = self.descripcion_var.get().strip()
        if not descripcion:
            messagebox.showerror("Falta la descripción", "Escribe una descripción para el movimiento.")
            return

        try:
            importe = Decimal(self.importe_var.get().strip().replace(",", "."))
            if not importe.is_finite() or importe <= 0:
                raise ValueError
            centavos = importe * 100
            if centavos != centavos.to_integral_value():
                messagebox.showerror("Importe no válido", "Usa como máximo dos decimales.")
                return
        except (InvalidOperation, ValueError):
            messagebox.showerror("Importe no válido", "Escribe un importe mayor que cero.")
            return

        tipo = self.tipo_var.get().lower()
        conexion.execute(
            "INSERT INTO movimientos (usuario_id, tipo, descripcion, monto_centavos) "
            "VALUES (?, ?, ?, ?)",
            (self.usuario_id, tipo, descripcion, int(centavos))
        )
        conexion.commit()
        self.descripcion_var.set("")
        self.importe_var.set("")
        self.actualizar_resumen()
        self.actualizar_historial()

    def actualizar_historial(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        movimientos = conexion.execute("""
            SELECT fecha, tipo, descripcion, monto_centavos
            FROM movimientos
            WHERE usuario_id = ?
            ORDER BY id DESC
        """, (self.usuario_id,)).fetchall()
        for fecha, tipo, descripcion, importe in movimientos:
            self.tabla.insert("", "end", values=(
                fecha, tipo.capitalize(), descripcion, self.dinero(importe)
            ))

    def actualizar_estado_moneda(self):
        cantidad = conexion.execute(
            "SELECT COUNT(*) FROM movimientos WHERE usuario_id = ?",
            (self.usuario_id,)
        ).fetchone()[0]
        if cantidad:
            self.selector_moneda.configure(state="disabled")
            self.boton_moneda.configure(state="disabled")
            self.estado_moneda.configure(
                text=f"Moneda: {self.moneda}. No se cambia para mantener consistentes los movimientos."
            )
        else:
            self.selector_moneda.configure(state="readonly")
            self.boton_moneda.configure(state="normal")
            self.estado_moneda.configure(
                text="Elige la moneda antes de registrar movimientos."
                if self.moneda is None else f"Moneda actual: {self.moneda}."
            )

    def actualizar_etiqueta_moneda(self):
        if hasattr(self, "moneda_form_label"):
            self.moneda_form_label.configure(text=self.moneda or "")

    def guardar_moneda(self):
        moneda = self.moneda_var.get().strip().upper()
        if moneda not in self.MONEDAS:
            messagebox.showerror("Moneda no válida", "Selecciona una moneda de la lista.")
            return
        conexion.execute("""
            INSERT INTO preferencias_financieras (usuario_id, moneda) VALUES (?, ?)
            ON CONFLICT(usuario_id) DO UPDATE SET moneda = excluded.moneda
        """, (self.usuario_id, moneda))
        conexion.commit()
        self.moneda = moneda
        self.actualizar_estado_moneda()
        self.actualizar_etiqueta_moneda()
        self.actualizar_resumen()
        messagebox.showinfo("Moneda guardada", f"Se usará {moneda} para esta cuenta.")

    def cerrar(self):
        conexion.close()
        self.ventana.destroy()


def main():
    ventana = tk.Tk()
    GestorFinanzas(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()