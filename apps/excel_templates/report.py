"""
Reporte de lo que no se pudo replicar.

Regla del modulo: nada se descarta en silencio. Si una caracteristica se
encuentra pero no se sabe reproducir, se anota aqui y se deja el dato en
`extra_json` de su tabla. Asi el reporte es la lista de trabajo de la Fase 2 y
unQA puede detectar que una plantilla salio degradada.
"""

from dataclasses import dataclass, field, asdict


NIVEL_SOPORTADO = "soportado"
NIVEL_DEGRADADO = "degradado"
NIVEL_NO_SOPORTADO = "no_soportado"


@dataclass
class Reporte:
    """Acumula avisos de una captura o una exportacion."""

    #: Lista de dicts: {"nivel", "feature", "detalle", "sheet"}
    entradas: list = field(default_factory=list)

    def _agregar(self, nivel, feature, detalle, sheet=""):
        self.entradas.append(
            {
                "nivel": nivel,
                "feature": feature,
                "detalle": str(detalle),
                "sheet": str(sheet or ""),
            }
        )

    def soportado(self, feature, detalle="", sheet=""):
        self._agregar(NIVEL_SOPORTADO, feature, detalle, sheet)

    def degradado(self, feature, detalle, sheet=""):
        self._agregar(NIVEL_DEGRADADO, feature, detalle, sheet)

    def no_soportado(self, feature, detalle, sheet=""):
        self._agregar(NIVEL_NO_SOPORTADO, feature, detalle, sheet)

    def catatan(self, feature, detalle, sheet=""):
        """Aviso sin perdida de informacion: el dato queda en `extra_json`."""

        self._agregar(NIVEL_DEGRADADO, feature, f"guardado en extra_json: {detalle}", sheet)

    @property
    def hay_degradaciones(self):
        return any(
            entrada["nivel"] in (NIVEL_DEGRADADO, NIVEL_NO_SOPORTADO)
            for entrada in self.entradas
        )

    def por_nivel(self, nivel):
        return [e for e in self.entradas if e["nivel"] == nivel]

    def como_dict(self):
        return {
            "entradas": list(self.entradas),
            "hay_degradaciones": self.hay_degradaciones,
        }

    def resumen(self):
        """Conteo por nivel, para el log y el reporte final."""

        conteo = {}
        for entrada in self.entradas:
            conteo[entrada["nivel"]] = conteo.get(entrada["nivel"], 0) + 1
        return conteo

    def __str__(self):
        partes = [f"{nivel}={conteo}" for nivel, conteo in sorted(self.resumen().items())]
        return ", ".join(partes) if partes else "sin hallazgos"