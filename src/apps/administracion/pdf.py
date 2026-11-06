"""Generador nativo de reportes PDF (estándar PDF 1.4) para el listado de inscriptos aprobados.

Implementa la Extensión 1 del proyecto utilizando únicamente la biblioteca
estándar de Python (sin dependencias externas), generando un documento PDF
vectorial en tamaño A4 con la identidad visual de SIGA y codificación
WinAnsi (cp1252) para caracteres en español.
"""
from collections import defaultdict
from datetime import datetime
try:
    from django.utils import timezone
except ImportError:  # pragma: no cover
    timezone = None

# Dimensiones A4 en puntos tipográficos (1 pt = 1/72 pulgada)
ANCHO_A4 = 595.28
ALTO_A4 = 841.89
MARGEN_X = 36.0
ANCHO_UTIL = ANCHO_A4 - 2 * MARGEN_X


def _escapar_pdf(texto: str) -> bytes:
    """Codifica texto en cp1252 (WinAnsiEncoding) y escapa delimitadores PDF."""
    limpio = (texto or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    limpio = limpio.replace("\r", " ").replace("\n", " ")
    return limpio.encode("cp1252", errors="replace")


def _truncar(texto: str, max_chars: int) -> str:
    texto = (texto or "").strip()
    if len(texto) <= max_chars:
        return texto
    return texto[: max_chars - 1].rstrip() + "…"


class _LienzoPagina:
    """Acumula primitivas gráficas y de texto PDF para una página A4."""

    def __init__(self):
        self.comandos: list[bytes] = []

    def rect(self, x: float, y_top: float, w: float, h: float, fill_rgb=None, stroke_rgb=None, line_width=0.6):
        """Dibuja un rectángulo usando coordenadas medidas desde el borde superior."""
        y_pdf = ALTO_A4 - y_top - h
        partes = [b"q"]
        if fill_rgb is not None:
            r, g, b = fill_rgb
            partes.append(f"{r:.3f} {g:.3f} {b:.3f} rg".encode("ascii"))
        if stroke_rgb is not None:
            r, g, b = stroke_rgb
            partes.append(f"{r:.3f} {g:.3f} {b:.3f} RG {line_width:.2f} w".encode("ascii"))
        op = b"B" if (fill_rgb and stroke_rgb) else (b"f" if fill_rgb else b"S")
        partes.append(f"{x:.2f} {y_pdf:.2f} {w:.2f} {h:.2f} re {op.decode('ascii')}".encode("ascii"))
        partes.append(b"Q")
        self.comandos.append(b" ".join(partes))

    def linea(self, x1: float, y1_top: float, x2: float, y2_top: float, stroke_rgb=(0.80, 0.84, 0.88), line_width=0.5):
        y1 = ALTO_A4 - y1_top
        y2 = ALTO_A4 - y2_top
        r, g, b = stroke_rgb
        cmd = f"q {r:.3f} {g:.3f} {b:.3f} RG {line_width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q"
        self.comandos.append(cmd.encode("ascii"))

    def texto(self, x: float, y_top: float, cadena: str, fuente="F1", tam=9.5, rgb=(0.12, 0.16, 0.23)):
        """Escribe una línea de texto en la posición (x, y_top desde arriba)."""
        y_pdf = ALTO_A4 - y_top
        r, g, b = rgb
        prefijo = f"BT /{fuente} {tam:.1f} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x:.2f} {y_pdf:.2f} Tm (".encode("ascii")
        self.comandos.append(prefijo + _escapar_pdf(cadena) + b") Tj ET")

    def contenido(self) -> bytes:
        return b"\n".join(self.comandos)


def _ensamblar_pdf(paginas: list[_LienzoPagina]) -> bytes:
    """Empaqueta una lista de páginas en un archivo PDF 1.4 válido."""
    objetos: list[bytes] = []

    def agregar_objeto(cuerpo: bytes) -> int:
        objetos.append(cuerpo)
        return len(objetos)

    # 1..3: Fuentes estándar Type1 con WinAnsiEncoding (soportan tildes, ñ, º, ·)
    id_f1 = agregar_objeto(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    id_f2 = agregar_objeto(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    id_f3 = agregar_objeto(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")

    # Reservamos el objeto Pages
    id_pages = agregar_objeto(b"")
    ids_pagina: list[int] = []

    for lienzo in paginas:
        flujo = lienzo.contenido()
        id_stream = agregar_objeto(
            f"<< /Length {len(flujo)} >>\nstream\n".encode("ascii") + flujo + b"\nendstream"
        )
        cuerpo_pagina = (
            f"<< /Type /Page /Parent {id_pages} 0 R "
            f"/MediaBox [0 0 {ANCHO_A4:.2f} {ALTO_A4:.2f}] "
            f"/Resources << /Font << /F1 {id_f1} 0 R /F2 {id_f2} 0 R /F3 {id_f3} 0 R >> >> "
            f"/Contents {id_stream} 0 R >>"
        ).encode("ascii")
        ids_pagina.append(agregar_objeto(cuerpo_pagina))

    kids = " ".join(f"{pid} 0 R" for pid in ids_pagina)
    objetos[id_pages - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(ids_pagina)} >>".encode("ascii")

    id_catalog = agregar_objeto(f"<< /Type /Catalog /Pages {id_pages} 0 R >>".encode("ascii"))
    id_info = agregar_objeto(
        b"<< /Title (SIGA - Listado de Inscriptos Aprobados) "
        b"/Author (SIGA - Instituto Tecnico Superior N. 1) "
        b"/Creator (SIGA Django PDF) >>"
    )

    # Construcción del binario con tabla xref
    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for indice, obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida.extend(f"{indice} 0 obj\n".encode("ascii"))
        salida.extend(obj)
        salida.extend(b"\nendobj\n")

    inicio_xref = len(salida)
    salida.extend(f"xref\n0 {len(objetos) + 1}\n".encode("ascii"))
    salida.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        salida.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    salida.extend(
        f"trailer\n<< /Size {len(objetos) + 1} /Root {id_catalog} 0 R /Info {id_info} 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(salida)


def generar_pdf_aprobados(*, periodo, solicitudes, carrera_filtrada=None, generado_en: datetime | None = None) -> bytes:
    """Genera el PDF con los aspirantes aprobados agrupados por carrera."""
    # Paleta institucional de SIGA
    NAVY = (0.075, 0.161, 0.294)     # #13294B
    BLUE = (0.180, 0.373, 0.780)     # #2E5FC7
    MINT = (0.275, 0.827, 0.541)     # #46D38A
    GRAY_BG = (0.957, 0.965, 0.976)  # #F4F6F9
    BORDER = (0.800, 0.835, 0.882)   # #CBD5E1
    TEXT = (0.118, 0.161, 0.231)     # #1E293B
    MUTED = (0.392, 0.455, 0.545)    # #64748B
    WHITE = (1.0, 1.0, 1.0)

    ahora = generado_en or (timezone.localtime(timezone.now()) if timezone else datetime.now())
    fecha_emision = ahora.strftime("%d/%m/%Y %H:%M")
    nombre_periodo = periodo.nombre if periodo else "Sin período activo"
    alcance_carrera = carrera_filtrada.nombre if carrera_filtrada else "Todas las carreras"

    # Agrupar solicitudes por carrera preservando orden alfabético de carrera y apellido
    grupos: dict[str, list] = defaultdict(list)
    metadatos_carrera: dict[str, str] = {}
    lista_solicitudes = list(solicitudes)
    for s in lista_solicitudes:
        carrera_obj = s.periodo_plan.plan.carrera
        clave = carrera_obj.nombre
        grupos[clave].append(s)
        plan = s.periodo_plan.plan
        metadatos_carrera[clave] = (
            f"Plan {plan.codigo} ({plan.resolucion})" if plan.resolucion else f"Plan {plan.codigo}"
        )

    paginas: list[_LienzoPagina] = []

    def nueva_pagina(es_primera: bool = False) -> tuple[_LienzoPagina, float]:
        p = _LienzoPagina()
        paginas.append(p)
        # Encabezado institucional
        p.rect(0, 0, ANCHO_A4, 58, fill_rgb=NAVY)
        p.rect(0, 58, ANCHO_A4, 3, fill_rgb=MINT)
        p.texto(MARGEN_X, 26, "SIGA.", fuente="F2", tam=18, rgb=WHITE)
        p.texto(MARGEN_X + 54, 25, "Sistema Integral de Gestión Académica", fuente="F2", tam=11, rgb=WHITE)
        p.texto(
            MARGEN_X + 54,
            40,
            "Instituto Técnico Superior N.º 1 · Viedma, Provincia de Río Negro",
            fuente="F1",
            tam=8.5,
            rgb=(0.80, 0.85, 0.92),
        )
        p.texto(ANCHO_A4 - MARGEN_X - 125, 34, f"Emitido: {fecha_emision}", fuente="F1", tam=8.5, rgb=WHITE)

        y = 82.0
        if es_primera:
            p.texto(MARGEN_X, y, "Listado de Inscriptos Aprobados", fuente="F2", tam=15, rgb=NAVY)
            y += 16
            p.rect(MARGEN_X, y, ANCHO_UTIL, 36, fill_rgb=GRAY_BG, stroke_rgb=BORDER)
            p.texto(MARGEN_X + 10, y + 14, f"Período: {nombre_periodo}", fuente="F2", tam=9.5, rgb=TEXT)
            p.texto(MARGEN_X + 210, y + 14, f"Filtro: {_truncar(alcance_carrera, 48)}", fuente="F1", tam=9.0, rgb=TEXT)
            p.texto(
                MARGEN_X + 10,
                y + 28,
                f"Total de ingresantes aprobados en el reporte: {len(lista_solicitudes)}",
                fuente="F1",
                tam=8.5,
                rgb=MUTED,
            )
            y += 52
        return p, y

    def dibujar_encabezado_tabla(p: _LienzoPagina, y: float) -> float:
        p.rect(MARGEN_X, y, ANCHO_UTIL, 18, fill_rgb=(0.91, 0.93, 0.96), stroke_rgb=BORDER)
        p.texto(MARGEN_X + 6, y + 12, "TRÁMITE", fuente="F2", tam=7.5, rgb=NAVY)
        p.texto(MARGEN_X + 82, y + 12, "DNI", fuente="F2", tam=7.5, rgb=NAVY)
        p.texto(MARGEN_X + 140, y + 12, "APELLIDO Y NOMBRE", fuente="F2", tam=7.5, rgb=NAVY)
        p.texto(MARGEN_X + 278, y + 12, "CORREO ELECTRÓNICO", fuente="F2", tam=7.5, rgb=NAVY)
        p.texto(MARGEN_X + 398, y + 12, "TELÉFONO", fuente="F2", tam=7.5, rgb=NAVY)
        p.texto(MARGEN_X + 478, y + 12, "ACEPTADO", fuente="F2", tam=7.5, rgb=NAVY)
        return y + 18

    lienzo, y_actual = nueva_pagina(es_primera=True)
    LIMITE_Y = ALTO_A4 - 56.0

    if not lista_solicitudes:
        lienzo.rect(MARGEN_X, y_actual, ANCHO_UTIL, 44, fill_rgb=WHITE, stroke_rgb=BORDER)
        lienzo.texto(
            MARGEN_X + 14,
            y_actual + 25,
            "No se registran aspirantes en estado Aceptado para el período y filtros seleccionados.",
            fuente="F1",
            tam=10,
            rgb=MUTED,
        )
    else:
        for nombre_carrera, items in grupos.items():
            # Si no entra el bloque de título de carrera + cabecera + al menos 1 fila, saltar de página
            if y_actual + 62 > LIMITE_Y:
                lienzo, y_actual = nueva_pagina(es_primera=False)

            # Encabezado de grupo (carrera)
            lienzo.rect(MARGEN_X, y_actual, ANCHO_UTIL, 22, fill_rgb=NAVY)
            lienzo.texto(
                MARGEN_X + 8,
                y_actual + 14.5,
                _truncar(nombre_carrera, 74),
                fuente="F2",
                tam=9.0,
                rgb=WHITE,
            )
            info_plan = f"{metadatos_carrera.get(nombre_carrera, '')} · {len(items)} aprobado(s)"
            lienzo.texto(ANCHO_A4 - MARGEN_X - 175, y_actual + 14.5, _truncar(info_plan, 45), fuente="F1", tam=8.0, rgb=MINT)
            y_actual += 22

            y_actual = dibujar_encabezado_tabla(lienzo, y_actual)

            for idx, solicitud in enumerate(items):
                if y_actual + 19 > LIMITE_Y:
                    lienzo, y_actual = nueva_pagina(es_primera=False)
                    lienzo.texto(
                        MARGEN_X,
                        y_actual,
                        f"{_truncar(nombre_carrera, 65)} (continuación)",
                        fuente="F2",
                        tam=9.0,
                        rgb=BLUE,
                    )
                    y_actual += 6
                    y_actual = dibujar_encabezado_tabla(lienzo, y_actual)

                fondo_fila = GRAY_BG if idx % 2 == 1 else WHITE
                lienzo.rect(MARGEN_X, y_actual, ANCHO_UTIL, 18, fill_rgb=fondo_fila, stroke_rgb=BORDER, line_width=0.35)

                persona = solicitud.persona
                apellido_nombre = f"{persona.apellido}, {persona.nombre}"
                fecha_res = (
                    (timezone.localtime(solicitud.fecha_revision) if timezone else solicitud.fecha_revision).strftime("%d/%m/%Y")
                    if solicitud.fecha_revision
                    else "-"
                )

                lienzo.texto(MARGEN_X + 6, y_actual + 12, solicitud.numero, fuente="F3", tam=8.0, rgb=NAVY)
                lienzo.texto(MARGEN_X + 82, y_actual + 12, persona.dni, fuente="F3", tam=8.5, rgb=TEXT)
                lienzo.texto(MARGEN_X + 140, y_actual + 12, _truncar(apellido_nombre, 26), fuente="F2", tam=8.5, rgb=TEXT)
                lienzo.texto(MARGEN_X + 278, y_actual + 12, _truncar(persona.email, 26), fuente="F1", tam=8.0, rgb=TEXT)
                lienzo.texto(MARGEN_X + 398, y_actual + 12, _truncar(persona.telefono, 18), fuente="F1", tam=8.0, rgb=TEXT)
                lienzo.texto(MARGEN_X + 478, y_actual + 12, fecha_res, fuente="F1", tam=8.0, rgb=MUTED)
                y_actual += 18

            y_actual += 14

    # Pie de página con numeración total en cada hoja
    total_paginas = len(paginas)
    for num, p in enumerate(paginas, start=1):
        p.linea(MARGEN_X, ALTO_A4 - 36, ANCHO_A4 - MARGEN_X, ALTO_A4 - 36, stroke_rgb=BORDER)
        p.texto(
            MARGEN_X,
            ALTO_A4 - 22,
            "SIGA · ITS N.º 1 Viedma — Nómina de aspirantes aprobados para Secretaría y Referente TIC",
            fuente="F1",
            tam=7.5,
            rgb=MUTED,
        )
        p.texto(
            ANCHO_A4 - MARGEN_X - 58,
            ALTO_A4 - 22,
            f"Página {num} de {total_paginas}",
            fuente="F2",
            tam=8.0,
            rgb=NAVY,
        )

    return _ensamblar_pdf(paginas)
