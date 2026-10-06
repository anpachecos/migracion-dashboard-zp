"""
Clasificacion de celdas: cabecera, leyenda o dato.

Es la unica parte del motor que decide que texto sobrevive a la plantilla, y
por eso tiene que ser conservadora. La regla es simple: ante la duda, la
celda es `data` y se vacia. Filtrar informacion por un error de heuristica es
irreversible; perder una cabecera se corrige a mano (`role` es editable).

Los criterios se basan de la estructura que Excel ya trae, no del contenido:

- una celda es `HEADER` si esta en la fila inicial del rango de un
  autofiltro, o si cumple al menos dos de: negrita, relleno distinto al de las
  filas siguientes, o alto de fila mayor que el resto;
- una celda es `LEGEND` si pertenece a un bloque pequeno y aislado con relleno
  de color (menos de ~30 celdas), tipicamente el glosario que explica los
  colores de una hoja de datos;
- el resto es `DATA`.

Ningun nombre de hoja, columna o color esta escrito aqui: el mismo Excel con
otros nombres debe clasificarse igual.
"""

# Cantidad maxima de celdas para que un bloque con relleno cuente como leyenda.
MAXIMO_CELDAS_LEYENDA = 30

# Segundos de separacion a partir del cual se considera "aislado".
SEPARACION_LEYENDA = 2


def _tiene_relleno(relleno):
    """True si el relleno realmente pinta la celda."""

    if not relleno:
        return False
    if relleno.get("kind") != "pattern":
        return False
    patron = relleno.get("patternType")
    return patron not in (None, "none")


def _color_relleno(relleno):
    """Clave comparable del color de relleno (para saber si es distinto)."""

    if not _tiene_relleno(relleno):
        return None

    color = relleno.get("fgColor") or {}
    if not color:
        color = relleno.get("bgColor") or {}

    tipo = color.get("type")
    valor = color.get("value")
    tint = color.get("tint")

    if tipo == "rgb":
        base = str(valor or "").upper()
    elif tipo == "theme":
        base = f"tema:{valor}"
    elif tipo == "indexed":
        base = f"idx:{valor}"
    else:
        base = "auto"

    if tint:
        base = f"{base}:{tint}"

    return f"{relleno.get('patternType')}|{base}"


def clasificar_hoja(estilos_por_celda, filas_con_estilo, altura_fila,
                    fila_autofiltro=None):
    """
    Devuelve `{(fila, col): role}` para las celdas con estilo.

    Parametros:
        estilos_por_celda: dict `{(fila, col): {font, fill, ...}}`.
        filas_con_estilo: filas que tienen al menos una celda con estilo.
        altura_fila: dict `{fila: alto}`. Si falta, no se usa el criterio del
            alto y el resto de criterios siguen valiendo.
        fila_autofiltro: fila inicial del rango de autofiltro, si la hoja tiene.

    Devuelve roles en `roles.HEADER`/`LEGEND`/`DATA`/`UNKNOWN`.
    """

    roles = {}
    filas = sorted(filas_con_estilo)

    if not filas:
        return roles

    # Mapa fila -> {col: color de relleno}, para comparar con la fila siguiente.
    rellenos_por_fila = {}
    alturas = {fila: altura_fila.get(fila) for fila in filas if fila in altura_fila}
    alturas_validas = [h for h in alturas.values() if h]

    # Altura modal: la que se repite es "la normal" de la hoja, y una fila que
    # la supera es candidata a cabecera.
    if alturas_validas:
        conteo = {}
        for alto in alturas_validas:
            conteo[round(alto, 2)] = conteo.get(round(alto, 2), 0) + 1
        altura_normal = max(conteo, key=lambda a: conteo[a])
    else:
        altura_normal = None

    for fila in filas:
        celdas = {
            col: estilo
            for (f, col), estilo in estilos_por_celda.items()
            if f == fila
        }
        rellenos_por_fila[fila] = {
            col: _color_relleno(estilo.get("fill"))
            for col, estilo in celdas.items()
        }

    filas_leyenda = _detectar_bloques_leyenda(estilos_por_celda, filas)

    for fila in filas:
        celdas = {
            col: estilo
            for (f, col), estilo in estilos_por_celda.items()
            if f == fila
        }
        siguiente = rellenos_por_fila.get(fila + 1, {})

        for col, estilo in celdas.items():
            roles[(fila, col)] = _clasificar_celda(
                fila=fila,
                col=col,
                estilo=estilo,
                fila_autofiltro=fila_autofiltro,
                relleno_fila=rellenos_por_fila.get(fila, {}).get(col),
                relleno_siguiente=siguiente.get(col),
                altura_fila=alturas.get(fila),
                altura_normal=altura_normal,
                filas_leyenda=filas_leyenda,
                filas_totales=len(filas),
            )

    return roles


def completar_roles(roles_por_celda, celdas_presentes):
    """
    Rellena los huecos de celdas sin estilo con el rol de su fila.

    En una hoja de leyenda es normal que solo la primera columna lleve relleno
    y que el texto de la segunda quede sin estilo ninguno. Si el rol se mirara
    solo celda por celda, ese texto se perderia al exportar, y el motivo real es
    que la fila si es una leyenda.

    Solo se propaga cuando la fila entera es de un unico tipo y ese tipo
    conserva texto. En cuanto una fila mezcla roles, o todos son `DATA`, no se
    toca nada: la duda se resuelve hacia vaciar, que es la decision segura.
    """

    por_fila = {}
    for (fila, _col), rol in roles_por_celda.items():
        por_fila.setdefault(fila, set()).add(rol)

    propagables = {}
    for fila, roles_de_la_fila in por_fila.items():
        if len(roles_de_la_fila) == 1:
            unico = next(iter(roles_de_la_fila))
            if roles.es_texto(unico):
                propagables[fila] = unico

    resultado = dict(roles_por_celda)

    for (fila, col) in celdas_presentes:
        if (fila, col) in resultado:
            continue
        if fila in propagables:
            resultado[(fila, col)] = propagables[fila]

    return resultado


def _detectar_bloques_leyenda(estilos_por_celda, filas):
    """
    Filas que forman un bloque de leyenda.

    Un bloque es un grupo de filas consecutivas, con relleno de color, de
    pocas celdas y separado del resto por al menos `SEPARACION_LEYENDA` filas
    sin relleno. Esa combinacion distingue un glosario de una tabla de datos
    coloreada.
    """

    filas_por_rolleno = {}
    for (fila, col), estilo in estilos_por_celda.items():
        filas_por_rolleno.setdefault(fila, []).append((col, estilo))

    filas_con_color = {
        fila
        for fila, celdas in filas_por_rolleno.items()
        if any(_tiene_relleno(estilo.get("fill")) for _, estilo in celdas)
    }

    if not filas_con_color:
        return set()

    # Recorre las filas ordenadas buscando grupos cortos con relleno, separados
    # por al menos SEPARACION_LEYENDA filas limpias.
    ordenadas = sorted(filas)
    bloques = set()
    grupo_actual = []
    filas_limpias = 0

    def cerrar(grupo):
        if len(grupo) <= MAXIMO_CELDAS_LEYENDA:
            bloques.update(grupo)

    for fila in ordenadas:
        celdas = filas_por_rolleno.get(fila, [])
        tiene_color = any(_tiene_relleno(estilo.get("fill")) for _, estilo in celdas)

        if tiene_color:
            if filas_limpias >= SEPARACION_LEYENDA:
                cerrar(grupo_actual)
                grupo_actual = []
            grupo_actual.append(fila)
            filas_limpias = 0
        else:
            if grupo_actual:
                filas_limpias += 1

    cerrar(grupo_actual)
    return bloques


def _clasificar_celda(fila, col, estilo, fila_autofiltro, relleno_fila,
                      relleno_siguiente, altura_fila, altura_normal,
                      filas_leyenda, filas_totales):
    """Aplica los criterios y devuelve un rol."""

    if fila in filas_leyenda:
        return roles.LEGEND

    fuente = estilo.get("font") or {}
    criterios = 0

    # Criterio 1: negrita.
    if fuente.get("b"):
        criterios += 1

    # Criterio 2: relleno distinto al de la fila siguiente.
    if relleno_fila and relleno_fila != relleno_siguiente:
        criterios += 1

    # Criterio 3: alto de fila mayor que el resto.
    if altura_fila and altura_normal and altura_fila > altura_normal:
        criterios += 1

    # Estar en la fila inicial del autofiltro es senal fuerte: es la fila de
    # encabezados que Excel trato como tabla.
    if fila_autofiltro is not None and fila == fila_autofiltro:
        return roles.HEADER

    if criterios >= 2:
        return roles.HEADER

    # Una celda con texto pero sin ninguna senal de formato no se puede
    # clasificar con confianza: se deja como dato para no filtrar nada, y el
    # rol queda editable.
    if criterios == 0 and not _tiene_relleno(estilo.get("fill")):
        return roles.DATA

    return roles.DATA


class roles:
    """Nombres de rol, en minúscula para compararlos con `role` en la base."""

    HEADER = "HEADER"
    LEGEND = "LEGEND"
    DATA = "DATA"
    UNKNOWN = "UNKNOWN"

    #: Roles cuyo texto se conserva al exportar.
    CONSERVAN_TEXTO = (HEADER, LEGEND)

    @staticmethod
    def es_texto(valor):
        return valor in roles.CONSERVAN_TEXTO