import os
from datetime import date
from decimal import Decimal, InvalidOperation

import flet as ft
import httpx


BACKGROUND = "#F2F5F0"
INK = "#173D35"
MUTED = "#65756E"
ACCENT = "#237A64"
EXPENSE = "#B65C4B"
WHITE = "#FFFFFF"
CATEGORIES = (
    "Vivienda", "Alimentacion", "Transporte", "Salud", "Educacion",
    "Ocio", "Servicios", "Salario", "Ventas", "Ahorro", "Otros",
)
METHODS = ("Efectivo", "Tarjeta", "Transferencia", "Domiciliacion", "Otro")


def border_all(width: int, color: str):
    if hasattr(ft, "Border") and hasattr(ft.Border, "all"):
        return ft.Border.all(width, color)
    return ft.border.all(width, color)


def get_storage(page):
    if hasattr(page, "client_storage"):
        return page.client_storage
    if not hasattr(page, "_app_storage"):
        page._app_storage = {}
    return page._app_storage


def storage_get(page, key, default=None):
    storage = get_storage(page)
    if hasattr(storage, "get"):
        return storage.get(key, default)
    return storage.get(key, default)


def storage_set(page, key, value):
    storage = get_storage(page)
    if hasattr(storage, "set"):
        storage.set(key, value)
        return
    storage[key] = value


def storage_remove(page, key):
    storage = get_storage(page)
    if hasattr(storage, "remove"):
        storage.remove(key)
        return
    storage.pop(key, None)


def money(cents: int, currency: str) -> str:
    return f"{Decimal(cents) / Decimal(100):,.2f} {currency}"


def main(page: ft.Page):
    page.title = "Gestor de Finanzas"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = BACKGROUND
    page.padding = 20
    page.window.min_width = 360
    page.window.min_height = 640
    page.theme = ft.Theme(color_scheme_seed=ACCENT)

    api_field = ft.TextField(
        label="Direccion del servidor", value=os.getenv("GESTOR_API_URL", "http://127.0.0.1:8000"),
        prefix_icon=ft.Icons.DNS_OUTLINED, keyboard_type=ft.KeyboardType.URL,
    )
    email_field = ft.TextField(label="Correo", keyboard_type=ft.KeyboardType.EMAIL)
    password_field = ft.TextField(
        label="Contrasena", password=True, can_reveal_password=True
    )
    currency_field = ft.TextField(label="Moneda (por ejemplo EUR)", value="EUR", max_length=3)
    notice = ft.Text(color=EXPENSE, size=13)
    state = {"token": "", "user": None, "register": False}

    def notify(text: str, error: bool = False):
        notice.value = text
        notice.color = EXPENSE if error else ACCENT
        page.update()

    def api_request(method: str, path: str, **kwargs):
        base_url = api_field.value.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("La direccion debe empezar por http:// o https://")
        headers = kwargs.pop("headers", {})
        if state["token"]:
            headers["Authorization"] = f"Bearer {state['token']}"
        response = httpx.request(
            method, base_url + path, headers=headers, timeout=12, **kwargs
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_error:
            detail = payload.get("detail", "No se pudo conectar con el servidor.")
            raise ValueError(str(detail))
        return payload

    def logout(_event=None):
        state["token"] = ""
        state["user"] = None
        storage_remove(page, "gestor_token")
        login_screen()

    def login_screen():
        page.appbar = None
        page.clean()
        notice.value = ""
        toggle = ft.TextButton(
            "Crear cuenta" if not state["register"] else "Ya tengo cuenta",
            on_click=toggle_registration,
        )
        controls = [
            ft.Text("GESTOR DE FINANZAS", size=12, weight=ft.FontWeight.BOLD,
                    color=ACCENT),
            ft.Text("Tus cuentas, en todos tus dispositivos", size=25,
                    weight=ft.FontWeight.BOLD, color=INK),
            ft.Text("Inicia sesion para consultar tus movimientos sincronizados.",
                    color=MUTED),
            api_field, email_field, password_field,
        ]
        if state["register"]:
            controls.append(currency_field)
        controls.extend([
            ft.FilledButton(
                "Crear cuenta" if state["register"] else "Iniciar sesion",
                on_click=submit_auth,
                style=ft.ButtonStyle(bgcolor=ACCENT, color=WHITE),
            ),
            toggle, notice,
        ])
        page.add(
            ft.Container(
                content=ft.Column(controls, spacing=16, tight=True,
                                  alignment=ft.MainAxisAlignment.CENTER),
                padding=24, bgcolor=WHITE, border_radius=12,
                border=border_all(1, "#DCE5DD"),
                width=520,
            )
        )
        page.update()

    def toggle_registration(_event=None):
        state["register"] = not state["register"]
        login_screen()

    def submit_auth(_event=None):
        try:
            payload = {
                "email": email_field.value.strip(),
                "password": password_field.value,
            }
            if state["register"]:
                payload["currency"] = currency_field.value.strip().upper()
                result = api_request("POST", "/auth/register", json=payload)
            else:
                result = api_request("POST", "/auth/login", json=payload)
            state["token"] = result["token"]
            state["user"] = result["user"]
            storage_set(page, "gestor_token", state["token"])
            storage_set(page, "gestor_api_url", api_field.value.strip().rstrip("/"))
            home_screen()
        except (httpx.HTTPError, ValueError, KeyError) as error:
            notify(str(error), error=True)

    def show_movement_detail(item):
        detail = ft.AlertDialog(
            modal=True,
            title=ft.Text(item["description"], color=INK, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                controls=[
                    ft.Text(f"{item['movement_date']}  |  {item['kind'].capitalize()}"),
                    ft.Text(f"Categoria: {item['category']}"),
                    ft.Text(f"Metodo: {item['method']}"),
                    ft.Text(f"Notas: {item['notes'] or 'Sin notas'}"),
                    ft.Text(
                        ("+" if item["kind"] == "ingreso" else "-")
                        + money(item["amount_cents"], state["user"]["currency"]),
                        color=ACCENT if item["kind"] == "ingreso" else EXPENSE,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                tight=True, spacing=12,
            ),
            actions=[ft.TextButton("Cerrar", on_click=lambda _e: page.pop_dialog())],
        )
        page.show_dialog(detail)

    def add_movement_dialog(_event=None):
        kind = ft.Dropdown(
            label="Tipo", value="gasto",
            options=[ft.dropdown.Option("gasto", "Gasto"),
                     ft.dropdown.Option("ingreso", "Ingreso")],
        )
        description = ft.TextField(label="Descripcion", autofocus=True, max_length=300)
        amount = ft.TextField(
            label=f"Importe ({state['user']['currency']})",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        category = ft.Dropdown(
            label="Categoria", value="Otros",
            options=[ft.dropdown.Option(value) for value in CATEGORIES],
        )
        movement_date = ft.TextField(label="Fecha (AAAA-MM-DD)", value=date.today().isoformat())
        method = ft.Dropdown(
            label="Metodo de pago", value="Efectivo",
            options=[ft.dropdown.Option(value) for value in METHODS],
        )
        notes = ft.TextField(label="Notas (opcional)", multiline=True, min_lines=2, max_lines=4)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nuevo movimiento", color=INK),
            content=ft.Container(
                width=480,
                content=ft.Column(
                    [kind, description, amount, category, movement_date, method, notes],
                    tight=True, scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def save(_event=None):
            try:
                parsed_amount = Decimal(amount.value.strip().replace(",", "."))
                if not parsed_amount.is_finite() or parsed_amount <= 0:
                    raise ValueError("El importe debe ser mayor que cero.")
                cents = parsed_amount * 100
                if cents != cents.to_integral_value():
                    raise ValueError("Usa como maximo dos decimales.")
                date.fromisoformat(movement_date.value.strip())
                api_request("POST", "/movements", json={
                    "kind": kind.value,
                    "description": description.value.strip(),
                    "amount_cents": int(cents),
                    "movement_date": movement_date.value.strip(),
                    "category": category.value,
                    "method": method.value,
                    "notes": notes.value.strip(),
                })
                page.pop_dialog()
                home_screen()
            except (InvalidOperation, ValueError, httpx.HTTPError) as error:
                notify(str(error) or "Revisa los datos del movimiento.", error=True)

        dialog.actions = [
            ft.TextButton("Cancelar", on_click=lambda _e: page.pop_dialog()),
            ft.FilledButton("Guardar", on_click=save),
        ]
        page.show_dialog(dialog)

    def home_screen():
        try:
            summary = api_request("GET", "/summary")
            movements = api_request("GET", "/movements")
        except (httpx.HTTPError, ValueError) as error:
            notify(str(error), error=True)
            return

        page.clean()
        user = state["user"]
        page.appbar = ft.AppBar(
            title=ft.Text("Finanzas", color=WHITE),
            bgcolor=INK,
            actions=[ft.IconButton(ft.Icons.LOGOUT, tooltip="Cerrar sesion",
                                   icon_color=WHITE, on_click=logout)],
        )

        def metric(title, value, color):
            return ft.Container(
                content=ft.Column([
                    ft.Text(title.upper(), size=10, weight=ft.FontWeight.BOLD,
                            color=MUTED),
                    ft.Text(value, size=19, weight=ft.FontWeight.BOLD, color=color),
                ], spacing=7, tight=True),
                bgcolor=WHITE, padding=16, border_radius=10,
                border=border_all(1, "#DCE5DD"),
                expand=True,
            )

        movement_rows = []
        for item in movements:
            positive = item["kind"] == "ingreso"
            amount_text = ("+" if positive else "-") + money(
                item["amount_cents"], user["currency"]
            )
            movement_rows.append(ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(item["description"], weight=ft.FontWeight.BOLD,
                                color=INK, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(f"{item['movement_date']} · {item['category']} · {item['method']}",
                                size=12, color=MUTED),
                    ], spacing=4, expand=True),
                    ft.Text(amount_text, color=ACCENT if positive else EXPENSE,
                            weight=ft.FontWeight.BOLD, size=13),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=14, bgcolor=WHITE, border_radius=8,
                border=border_all(1, "#DCE5DD"),
                on_click=lambda _e, entry=item: show_movement_detail(entry),
            ))

        content = ft.Column([
            ft.Text(user["email"], color=MUTED, size=12),
            ft.Text("Resumen", size=23, weight=ft.FontWeight.BOLD, color=INK),
            ft.ResponsiveRow([
                ft.Container(content=metric("Saldo", money(
                    summary["balance_cents"], user["currency"]
                ), INK), col={"xs": 12, "md": 4}),
                ft.Container(content=metric("Ingresos del mes", money(
                    summary["income_month_cents"], user["currency"]
                ), ACCENT), col={"xs": 12, "md": 4}),
                ft.Container(content=metric("Gastos del mes", money(
                    summary["expenses_month_cents"], user["currency"]
                ), EXPENSE), col={"xs": 12, "md": 4}),
            ], spacing=8, run_spacing=8),
            ft.Row([
                ft.Text("Movimientos", size=18, weight=ft.FontWeight.BOLD, color=INK,
                        expand=True),
                ft.FilledButton("+ Nuevo", on_click=add_movement_dialog),
            ]),
            ft.Column(movement_rows or [ft.Text("Todavia no hay movimientos.", color=MUTED)],
                      spacing=8),
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
        page.add(content)
        page.update()

    try:
        stored_api = storage_get(page, "gestor_api_url")
        if stored_api:
            api_field.value = stored_api
        saved_token = storage_get(page, "gestor_token")
        if saved_token:
            state["token"] = saved_token
            state["user"] = api_request("GET", "/me")
            home_screen()
            return
    except (httpx.HTTPError, ValueError):
        state["token"] = ""
        storage_remove(page, "gestor_token")
    login_screen()


if __name__ == "__main__":
    ft.app(target=main)