// Tarjeta de plantilla Excel del Monitor de Traspaso.
//
// Los dos botones de la tarjeta solo abren un dialogo. Toda la logica de la
// plantilla vive aca y en el backend, no en el template:
//
//   1. Al abrir "Exportar Excel" se pide la lista a `/plantillas-excel/` y se
//      pinta con un boton de descarga por plantilla. Si no hay ninguna, el
//      dialogo lo dice y ofrece importar: subir la primera es la unica forma
//      de tener algo que exportar.
//
//   2. Al abrir "Importar plantilla" se pide la misma lista y se ofrece elegir
//      sobre cual hacer la version nueva, o crear una plantilla nueva. El
//      destino viaja en `plantilla_id`; el nombre solo se usa si se eligio
//      "nueva".
//
//   3. El envio se hace con `fetch` y el `FormData` del formulario entero, que
//      ya lleva el token de CSRF. Un 409 (archivo ya capturado) deja el dialogo
//      abierto con el mensaje, porque la accion que corresponde es elegir otra
//      plantilla y no volver a intentar lo mismo.
//
// Los errores del backend se muestran tal cual: la captura devuelve 400 o 409
// con un texto pensado para leerse, y esconderlo seria peor que no importar.

window.TRX_PLANTILLA = (function () {

    let raiz = null;
    let dialogoExportar = null;
    let dialogoImportar = null;
    let formImportar = null;
    let listaDestino = null;
    let listaExportar = null;
    let errorImportar = null;
    let campoNombre = null;
    let campoArchivo = null;
    let casillaPublicar = null;
    let botonEnviar = null;
    let aviso = null;
    let destinoInicial = null;

    let urlPlantillas = "";
    let urlCapturar = "";
    let urlExportar = "";

    const TIEMPO_AVISO = 6000;

    // El id de relleno con el que la vista arma la ruta de exportacion. Tiene
    // que calcar el `0` de `views._contexto_de_plantillas`.
    const ID_RELLENO = "/0/exportar/";

    const DESTRINO_NUEVA = "nueva";

    function iniciar() {
        raiz = document.querySelector("[data-trx-plantilla]");
        if (!raiz) { return false; }

        // Los dialogos son hermanos de la tarjeta (no descendientes): se
        // buscan en document para que los botones no queden sin listener.
        dialogoExportar = document.querySelector("[data-trx-dlg-exportar]");
        dialogoImportar = document.querySelector("[data-trx-dlg-importar]");

        aviso = raiz.querySelector("[data-trx-plantilla-aviso]");
        urlPlantillas = raiz.getAttribute("data-url-plantillas") || "";
        urlCapturar = raiz.getAttribute("data-url-capturar") || "";
        urlExportar = raiz.getAttribute("data-url-exportar") || "";

        if (dialogoExportar) {
            listaExportar = dialogoExportar.querySelector("[data-trx-dlg-exportar-lista]");
            preparar(listaExportar);
        }

        if (dialogoImportar) {
            formImportar = dialogoImportar.querySelector("[data-trx-form-importar]");
            listaDestino = dialogoImportar.querySelector("[data-trx-dlg-destino-lista]");
            errorImportar = dialogoImportar.querySelector("[data-trx-error]");
            campoNombre = dialogoImportar.querySelector("[data-trx-nuevo-nombre]");
            campoArchivo = dialogoImportar.querySelector("[data-trx-archivo]");
            casillaPublicar = dialogoImportar.querySelector("[data-trx-publicar]");
            botonEnviar = dialogoImportar.querySelector("[data-trx-enviar]");

            formImportar.addEventListener("submit", enviar);
            campoArchivo.addEventListener("change", prellenarNombre);
            preparar(dialogoImportar);
        }

        const botonExportar = raiz.querySelector("[data-trx-plantilla-exportar]");
        const botonImportar = raiz.querySelector("[data-trx-plantilla-importar]");

        if (botonExportar && dialogoExportar) {
            botonExportar.addEventListener("click", function () {
                abrirExportar();
            });
        }

        if (botonImportar && dialogoImportar) {
            botonImportar.addEventListener("click", function () {
                abrirImportar();
            });
        }

        raiz.querySelectorAll("[data-trx-admin-cargar]").forEach(function (boton) {
            boton.addEventListener("click", function () {
                abrirImportar(boton.getAttribute("data-trx-admin-cargar"));
            });
        });

        return true;
    }

    // `dialog` se cierra solo con el boton que declara `[data-trx-cerrar]` si
    // ese boton esta en un `form method="dialog"`. Los que no, se cierran a
    // mano: por eso el atributo se busca en toda la pagina.
    function preparar(dialogo) {
        if (!dialogo) { return; }
        dialogo.querySelectorAll("[data-trx-cerrar]").forEach(function (boton) {
            boton.addEventListener("click", function () {
                dialogo.close();
            });
        });
    }

    /* ---------------------------------------------------------
       Datos
       --------------------------------------------------------- */

    function pedirPlantillas() {
        return fetch(urlPlantillas, { headers: { "X-Requested-With": "fetch" } })
            .then(function (respuesta) {
                if (!respuesta.ok) {
                    throw new Error("No se pudo consultar la lista de plantillas.");
                }
                return respuesta.json();
            })
            .then(function (datos) {
                return datos.plantillas || [];
            });
    }

    function abrirExportar() {
        dialogoExportar.showModal();
        pintarAviso(listaExportar, "Consultando plantillas…");
        pedirPlantillas().then(function (plantillas) {
            pintarExportables(plantillas);
        }).catch(function (error) {
            pintarAviso(listaExportar, error.message);
        });
    }

    function abrirImportar(plantillaId) {
        destinoInicial = plantillaId || null;
        dialogoImportar.showModal();
        limpiarError();
        pintarAviso(listaDestino, "Consultando plantillas…");
        pedirPlantillas().then(function (plantillas) {
            pintarDestinos(plantillas);
        }).catch(function (error) {
            pintarAviso(listaDestino, error.message);
        });
    }

    /* ---------------------------------------------------------
       Pintado de listas
       --------------------------------------------------------- */

    function pintarAviso(contenedor, texto) {
        contenedor.textContent = "";

        const parrafo = document.createElement("p");
        parrafo.className = "trx-dialog-aviso";
        parrafo.textContent = texto;
        contenedor.appendChild(parrafo);
    }

    function pintarExportables(plantillas) {
        listaExportar.textContent = "";

        if (!plantillas.length) {
            pintarAviso(
                listaExportar,
                "Todavia no hay ninguna plantilla capturada. Importa la primera " +
                "con el boton de al lado."
            );
            return;
        }

        const tabla = document.createElement("ul");
        tabla.className = "trx-lista-plantillas";

        plantillas.forEach(function (plantilla) {
            tabla.appendChild(filaExportable(plantilla));
        });

        listaExportar.appendChild(tabla);
    }

    function filaExportable(plantilla) {
        const fila = document.createElement("li");
        fila.className = "trx-fila-plantilla";

        const texto = document.createElement("div");
        texto.className = "trx-fila-plantilla-texto";

        const nombre = document.createElement("strong");
        nombre.textContent = plantilla.nombre;
        texto.appendChild(nombre);

        const detalle = document.createElement("span");
        detalle.className = "trx-sub";
        detalle.textContent =
            "version " + plantilla.version + " · " + plantilla.archivo;
        texto.appendChild(detalle);

        const enlace = document.createElement("button");
        enlace.className = "trx-btn trx-btn-acento";
        enlace.type = "button";
        enlace.textContent = "Preparar descarga";
        enlace.addEventListener("click", function () {
            if (!window.DASHBOARD_TRABAJOS) {
                informar("No se pudo iniciar el trabajo.", "error");
                return;
            }
            enlace.disabled = true;
            enlace.textContent = "Preparando…";
            dialogoExportar.close();
            window.DASHBOARD_TRABAJOS.crear("PLANTILLA_EXPORTAR", {
                plantilla_id: plantilla.id,
                version: plantilla.version,
            }).then(function () {
                informar("Exportación enviada. Revisa la campana cuando esté lista.", "ok");
            }).catch(function (error) {
                informar(error.message, "error");
            });
        });

        fila.appendChild(texto);
        fila.appendChild(enlace);
        return fila;
    }

    function pintarDestinos(plantillas) {
        listaDestino.textContent = "";
        campoNombre.disabled = false;

        if (plantillas.length) {
            plantillas.forEach(function (plantilla) {
                listaDestino.appendChild(
                    opcionDestino(
                        String(plantilla.id),
                        "Actualizar " + plantilla.nombre,
                        "Se creara la version " + (plantilla.version + 1) +
                        ". La vigente queda guardada."
                    )
                );
            });
        }

        listaDestino.appendChild(
            opcionDestino(DESTRINO_NUEVA, "Crear una plantilla nueva", "")
        );

        // Si no hay ninguna capturada, "crear nueva" es lo unico posible y
        // queda marcado de entrada.
        const primera = listaDestino.querySelector("input");
        const destinoFijado = destinoInicial && listaDestino.querySelector(
            'input[value="' + destinoInicial + '"]'
        );
        if (destinoFijado) {
            destinoFijado.checked = true;
            campoNombre.disabled = true;
        } else if (plantillas.length) {
            primera.checked = true;
            campoNombre.disabled = true;
        } else {
            listaDestino.querySelector(
                'input[value="' + DESTRINO_NUEVA + '"]'
            ).checked = true;
        }

        destinoInicial = null;

        listaDestino.onchange = function () {
            campoNombre.disabled = destinoElegido() !== DESTRINO_NUEVA;
        };
    }

    function opcionDestino(valor, etiqueta, ayuda) {
        const envoltorio = document.createElement("label");
        envoltorio.className = "trx-opcion";

        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "plantilla_id";
        radio.value = valor;
        envoltorio.appendChild(radio);

        const textos = document.createElement("span");
        const fuerte = document.createElement("strong");
        fuerte.textContent = etiqueta;
        textos.appendChild(fuerte);

        if (ayuda) {
            const chico = document.createElement("span");
            chico.className = "trx-sub";
            chico.textContent = ayuda;
            textos.appendChild(chico);
        }

        envoltorio.appendChild(textos);
        return envoltorio;
    }

    function destinoElegido() {
        const marcado = formImportar.querySelector(
            'input[name="plantilla_id"]:checked'
        );
        return marcado ? marcado.value : DESTRINO_NUEVA;
    }

    /* ---------------------------------------------------------
       Envío
       --------------------------------------------------------- */

    function prellenarNombre() {
        const archivo = campoArchivo.files && campoArchivo.files[0];
        if (!archivo) { return; }

        // El nombre por defecto es el del archivo sin extension, que es como
        // se llama la plantilla en la practica. Editable: el campo queda
        // habilitado solo si se eligio "crear nueva".
        campoNombre.value = archivo.name.replace(/\.(xlsx|xlsm)$/i, "");
    }

    function enviar(evento) {
        evento.preventDefault();

        limpiarError();

        if (!campoArchivo.files || !campoArchivo.files.length) {
            mostrarError("Elige el archivo .xlsx o .xlsm a importar.");
            return;
        }

        if (destinoElegido() === DESTRINO_NUEVA && !campoNombre.value.trim()) {
            mostrarError("Escribe el nombre de la plantilla nueva.");
            campoNombre.focus();
            return;
        }

        const cuerpo = new FormData(formImportar);
        // El radio "Crear una plantilla nueva" usa el valor visual "nueva",
        // pero `plantilla_id` solo acepta ids numericos. En ese caso el nombre
        // es el destino y el campo de id no debe viajar.
        if (destinoElegido() === DESTRINO_NUEVA) {
            cuerpo.delete("plantilla_id");
        }
        // `publicar` llega por el atributo `checked` del checkbox, asi que hay
        // que mandarlo a mano: un checkbox desmarcado no aparece en el FormData.
        cuerpo.set("publicar", casillaPublicar.checked ? "1" : "0");
        cuerpo.set("segundo_plano", "1");

        botonEnviar.disabled = true;
        botonEnviar.textContent = "Subiendo…";
        if (window.DASHBOARD_TRABAJOS) {
            window.DASHBOARD_TRABAJOS.avisar("Subiendo archivo. Puedes seguir usando el dashboard.");
        }
        dialogoImportar.close();

        fetch(urlCapturar, {
            method: "POST",
            body: cuerpo,
            headers: { "X-Requested-With": "fetch" },
        })
            .then(function (respuesta) {
                const tipo = respuesta.headers.get("content-type") || "";

                if (tipo.includes("application/json")) {
                    return respuesta.json().then(function (datos) {
                        return { ok: respuesta.ok, estado: respuesta.status, datos: datos };
                    });
                }

                // Django puede devolver HTML para un 500. No lo intentes
                // parsear como JSON: muestra un error util y deja el detalle
                // completo en la consola para diagnosticarlo.
                return respuesta.text().then(function (texto) {
                    console.error("Error HTTP al importar plantilla", respuesta.status, texto);
                    return {
                        ok: false,
                        estado: respuesta.status,
                        datos: { error: "El servidor devolvio un error inesperado (" + respuesta.status + ")." },
                    };
                });
            })
            .then(function (salida) {
                if (!salida.ok) {
                    // El dialogo se queda abierto a proposito: si el error es
                    // "ya capturado" o "no tienes permiso", lo que sirve es
                    // cambiar el destino o avisar, no cerrar y perder el
                    // archivo elegido.
                    mostrarError(mensajeDeError(salida));
                    return;
                }

                if (salida.datos.id) {
                    informar("Importación enviada. Revisa la campana cuando termine.", "ok");
                } else {
                    informar(resumenDeExito(salida.datos), "ok");
                }
                limpiarFormulario();
            })
            .catch(function () {
                dialogoImportar.showModal();
                mostrarError("No se pudo enviar el archivo al servidor.");
            })
            .finally(function () {
                botonEnviar.disabled = false;
                botonEnviar.textContent = "Importar";
            });
    }

    function mensajeDeError(salida) {
        if (salida.estado === 403) {
            return salida.datos.detail ||
                "No tienes permisos para subir plantillas.";
        }
        return salida.datos.error || "No se pudo importar la plantilla.";
    }

    function resumenDeExito(datos) {
        const donde = datos.creada
            ? "Plantilla '" + datos.nombre + "' creada"
            : "Plantilla '" + datos.nombre + "' actualizada";

        const estado = datos.vigente
            ? " y vigente"
            : " en borrador (no reemplaza la version vigente)";

        return donde + " con la version " + datos.version + estado + ".";
    }

    function limpiarFormulario() {
        formImportar.reset();
        campoNombre.value = "";
        limpiarError();
    }

    function mostrarError(texto) {
        if (!errorImportar) { return; }
        errorImportar.textContent = texto;
        errorImportar.hidden = false;
    }

    function limpiarError() {
        if (!errorImportar) { return; }
        errorImportar.textContent = "";
        errorImportar.hidden = true;
    }

    /* ---------------------------------------------------------
       Aviso de la tarjeta
       --------------------------------------------------------- */

    function informar(texto, estado) {
        if (!aviso) { return; }
        aviso.textContent = texto || "";
        aviso.setAttribute("data-estado", estado || "");
        if (!texto) { return; }

        window.clearTimeout(informar.temporizador);
        informar.temporizador = window.setTimeout(function () {
            aviso.textContent = "";
            aviso.removeAttribute("data-estado");
        }, TIEMPO_AVISO);
    }

    return { iniciar: iniciar };
})();
