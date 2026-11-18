"""Marca de eptus — lo que el backend necesita para hablar con la marca.

La marca vive en el frontend (``frontend/src/lib/components/Logo.svelte`` y
``frontend/static/logo-mark.svg``). Este módulo es la copia del lado del
servidor: los correos HTML se arman con strings (sin motor de plantillas), y
ahí no hay forma de importar un SVG del frontend — así que la geometría de la
"e" vive duplicada, en los dos lados, a propósito.

Si cambia la marca, cambian los dos lados en el mismo commit.
"""

from __future__ import annotations

#: Nombre de la marca.
NAME = "eptus"

#: La marca de eptus: "la pieza que encaja". Un marco (cuadrado con la
#: esquina superior derecha abierta en cuarto de circulo) y la pieza —un
#: circulo mas chico que el hueco— todavia por colocar. viewBox 0 0 32 32.
#: Dos tonos: el marco en la tinta, la pieza en el color de marca.
MARK_SVG = (
    '<svg width="26" height="26" viewBox="0 0 32 32" fill="none" '
    'stroke="{ink}" stroke-width="3.6" '
    'style="vertical-align:-5px;margin-right:8px">'
    '<path d="M21.5 3.5 H3.5 V28.5 H28.5 V10.5 A7 7 0 0 0 21.5 3.5 Z"/>'
    '<circle cx="21.5" cy="10.5" r="5.2" fill="{color}" stroke="none"/>'
    "</svg>"
)

#: Tinta y color de acción del tema claro (los mismos hex de app.css).
ACTION = "#4f46e5"
ACTION_HOVER = "#4338ca"
INK = "#1c1c2b"
INK_MUTED = "#4c4c63"


def brand_lockup(color: str = ACTION) -> str:
    """Marca + nombre, para la cabecera de los correos."""
    return (
        f'{MARK_SVG.format(color=color, ink=INK)}'
        f'<strong style="font-size:19px;letter-spacing:-.02em;color:{INK}">{NAME}</strong>'
    )
