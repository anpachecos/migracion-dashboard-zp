// Datos de relleno del Monitor de Traspaso C2D.
//
// Todo aquí es LITERAL y escrito a mano a propósito: cuando se conecte la
// base de datos, este archivo se borra y el `dataService` pasa a leer del
// endpoint "api". No hay Math.random ni generadores, así que la pantalla se
// ve exactamente igual en cada carga y los tests pueden comparar contra
// cifras fijas.
//
// Regla del módulo: el umbral de corte NO aparece como número acá ni en
// ninguna parte del JS. El test guardián `test_trx_service.py` rechaza el
// número del umbral suelto en estos archivos, así que los umbrales llegan
// desde la vista por `data-umbral-corte-min` y se usan concatenando.

window.MOCK = {

    // ---------------------------------------------------------
    // Pestaña 1 · Resumen mensual
    // ---------------------------------------------------------
    resumenMensual: {

        kpis: {
            cumplimiento: 83.5,
            promedioMin: 8.0,
            promedioMesAnteriorMin: 4.6,
            trx: 2400000,
            diasConDatos: 27,
            diasSobreMeta: 8,
            diasCriticos: [22, 23, 24],
            trxMayor15: 24309,
            reincidentes: 577
        },

        dias: [
            { fecha: "2026-08-01", cumplimiento: 91.1, promedioSeg: 218, maxSeg: 18240, trx: 98412, pctMayor15: 0.5 },
            { fecha: "2026-08-02", cumplimiento: 92.0, promedioSeg: 216, maxSeg: 16980, trx: 101233, pctMayor15: 0.4 },
            { fecha: "2026-08-03", cumplimiento: 85.2, promedioSeg: 224, maxSeg: 21470, trx: 97345, pctMayor15: 0.5 },
            { fecha: "2026-08-04", cumplimiento: 87.8, promedioSeg: 221, maxSeg: 19355, trx: 98890, pctMayor15: 0.4 },
            { fecha: "2026-08-05", cumplimiento: 89.1, promedioSeg: 219, maxSeg: 17820, trx: 102477, pctMayor15: 0.5 },
            { fecha: "2026-08-06", cumplimiento: 89.2, promedioSeg: 215, maxSeg: 24680, trx: 99102, pctMayor15: 0.4 },
            { fecha: "2026-08-07", cumplimiento: 87.9, promedioSeg: 223, maxSeg: 20915, trx: 97884, pctMayor15: 0.5 },
            { fecha: "2026-08-08", cumplimiento: 90.6, promedioSeg: 217, maxSeg: 16540, trx: 100933, pctMayor15: 0.4 },
            { fecha: "2026-08-09", cumplimiento: 92.3, promedioSeg: 214, maxSeg: 28110, trx: 101588, pctMayor15: 0.5 },
            { fecha: "2026-08-10", cumplimiento: 89.0, promedioSeg: 220, maxSeg: 19560, trx: 96471, pctMayor15: 0.4 },
            { fecha: "2026-08-11", cumplimiento: 89.0, promedioSeg: 222, maxSeg: 22980, trx: 99836, pctMayor15: 0.5 },
            { fecha: "2026-08-12", cumplimiento: 89.2, promedioSeg: 218, maxSeg: 17640, trx: 103219, pctMayor15: 0.4 },
            { fecha: "2026-08-13", cumplimiento: 89.2, promedioSeg: 216, maxSeg: 25310, trx: 98605, pctMayor15: 0.5 },
            { fecha: "2026-08-14", cumplimiento: 88.9, promedioSeg: 224, maxSeg: 18890, trx: 97348, pctMayor15: 0.4 },
            { fecha: "2026-08-15", cumplimiento: 91.7, promedioSeg: 215, maxSeg: 16120, trx: 101744, pctMayor15: 0.5 },
            { fecha: "2026-08-16", cumplimiento: 94.3, promedioSeg: 213, maxSeg: 29840, trx: 99562, pctMayor15: 0.4 },
            { fecha: "2026-08-17", cumplimiento: 90.5, promedioSeg: 219, maxSeg: 20170, trx: 100286, pctMayor15: 0.5 },
            { fecha: "2026-08-18", cumplimiento: 88.8, promedioSeg: 221, maxSeg: 17230, trx: 98310, pctMayor15: 0.4 },
            { fecha: "2026-08-19", cumplimiento: 87.7, promedioSeg: 225, maxSeg: 24190, trx: 102845, pctMayor15: 0.5 },
            { fecha: "2026-08-20", cumplimiento: 89.0, promedioSeg: 217, maxSeg: 15980, trx: 97193, pctMayor15: 0.4 },
            { fecha: "2026-08-21", cumplimiento: 88.9, promedioSeg: 221, maxSeg: 15127, trx: 100532, pctMayor15: 0.4 },
            { fecha: "2026-08-22", cumplimiento: 8.1, promedioSeg: 410, maxSeg: 32531, trx: 10221, pctMayor15: 9.7 },
            { fecha: "2026-08-23", cumplimiento: 26.1, promedioSeg: 320, maxSeg: 26140, trx: 2004, pctMayor15: 6.2 },
            { fecha: "2026-08-24", cumplimiento: 70.0, promedioSeg: 298, maxSeg: 28879, trx: 101813, pctMayor15: 3.1 },
            { fecha: "2026-08-25", cumplimiento: 89.2, promedioSeg: 219, maxSeg: 14196, trx: 99538, pctMayor15: 0.4 },
            { fecha: "2026-08-26", cumplimiento: 88.4, promedioSeg: 220, maxSeg: 28473, trx: 96523, pctMayor15: 0.5 },
            { fecha: "2026-08-27", cumplimiento: 90.4, promedioSeg: 220, maxSeg: 21932, trx: 100183, pctMayor15: 0.4 }
        ],

        meses: [
            { mes: "2026-01", promedioMin: 8.27, pctIncumplimiento: 14.2 },
            { mes: "2026-02", promedioMin: 5.67, pctIncumplimiento: 12.4 },
            { mes: "2026-03", promedioMin: 6.32, pctIncumplimiento: 13.4 },
            { mes: "2026-04", promedioMin: 4.27, pctIncumplimiento: 11.3 },
            { mes: "2026-05", promedioMin: 5.22, pctIncumplimiento: 11.2 },
            { mes: "2026-06", promedioMin: 4.42, pctIncumplimiento: 11.1 },
            { mes: "2026-07", promedioMin: 4.61, pctIncumplimiento: 10.0 },
            { mes: "2026-08", promedioMin: 8.01, pctIncumplimiento: 16.5 }
        ]
    },

    // ---------------------------------------------------------
    // Pestaña 2 · Resumen diario
    // ---------------------------------------------------------
    resumenDiario: {

        kpis: {
            cumplimiento: 90.4,
            deltaPP: 2.0,
            promedioSeg: 220,
            maxSeg: 21932,
            maxDetalle: "Parada 1 / (M) Zapadores",
            trx: 100183,
            trxSobre5: 9602,
            dispFueraSLA: 137,
            dispTotal: 1012
        },

        porHora: [
            { hora: 5, promedioMin: 3.20 },
            { hora: 6, promedioMin: 3.15 },
            { hora: 7, promedioMin: 3.17 },
            { hora: 8, promedioMin: 3.24 },
            { hora: 9, promedioMin: 3.28 },
            { hora: 10, promedioMin: 3.46 },
            { hora: 11, promedioMin: 3.32 },
            { hora: 12, promedioMin: 8.15 },
            { hora: 13, promedioMin: 5.01 },
            { hora: 14, promedioMin: 3.57 },
            { hora: 15, promedioMin: 4.04 },
            { hora: 16, promedioMin: 3.57 },
            { hora: 17, promedioMin: 4.02 },
            { hora: 18, promedioMin: 3.37 },
            { hora: 19, promedioMin: 3.38 },
            { hora: 20, promedioMin: 4.18 },
            { hora: 21, promedioMin: 3.35 },
            { hora: 22, promedioMin: 3.10 }
        ],

        severidad: { ok: 875, atencion: 78, alto: 36, critico: 23 },

        operadorHora: [
            { operador: "U1-Suburbus", horas: [
                { hora: 5, promedioMin: 3.10 }, { hora: 6, promedioMin: 3.05 }, { hora: 7, promedioMin: 3.18 },
                { hora: 8, promedioMin: 3.22 }, { hora: 9, promedioMin: 3.15 }, { hora: 10, promedioMin: 3.40 },
                { hora: 11, promedioMin: 3.28 }, { hora: 12, promedioMin: 7.85 }, { hora: 13, promedioMin: 4.20 },
                { hora: 14, promedioMin: 3.35 }, { hora: 15, promedioMin: 3.62 }, { hora: 16, promedioMin: 3.30 },
                { hora: 17, promedioMin: 3.48 }, { hora: 18, promedioMin: 3.25 }, { hora: 19, promedioMin: 3.20 },
                { hora: 20, promedioMin: 3.55 }, { hora: 21, promedioMin: 3.30 }, { hora: 22, promedioMin: 3.08 }
            ] },
            { operador: "U2-Alsacia", horas: [
                { hora: 5, promedioMin: 3.25 }, { hora: 6, promedioMin: 3.18 }, { hora: 7, promedioMin: 3.30 },
                { hora: 8, promedioMin: 3.52 }, { hora: 9, promedioMin: 3.28 }, { hora: 10, promedioMin: 3.52 },
                { hora: 11, promedioMin: 3.35 }, { hora: 12, promedioMin: 8.10 }, { hora: 13, promedioMin: 4.35 },
                { hora: 14, promedioMin: 3.48 }, { hora: 15, promedioMin: 3.70 }, { hora: 16, promedioMin: 3.40 },
                { hora: 17, promedioMin: 3.55 }, { hora: 18, promedioMin: 3.32 }, { hora: 19, promedioMin: 3.26 },
                { hora: 20, promedioMin: 3.62 }, { hora: 21, promedioMin: 3.38 }, { hora: 22, promedioMin: 3.12 }
            ] },
            { operador: "U5-Metbus", horas: [
                { hora: 5, promedioMin: 2.95 }, { hora: 6, promedioMin: 2.88 }, { hora: 7, promedioMin: 3.02 },
                { hora: 8, promedioMin: 3.15 }, { hora: 9, promedioMin: 3.05 }, { hora: 10, promedioMin: 3.28 },
                { hora: 11, promedioMin: 3.10 }, { hora: 12, promedioMin: 7.60 }, { hora: 13, promedioMin: 4.05 },
                { hora: 14, promedioMin: 3.22 }, { hora: 15, promedioMin: 3.50 }, { hora: 16, promedioMin: 3.18 },
                { hora: 17, promedioMin: 3.40 }, { hora: 18, promedioMin: 3.12 }, { hora: 19, promedioMin: 3.08 },
                { hora: 20, promedioMin: 3.42 }, { hora: 21, promedioMin: 3.20 }, { hora: 22, promedioMin: 2.95 }
            ] },
            { operador: "U8-US1", horas: [
                { hora: 5, promedioMin: 3.35 }, { hora: 6, promedioMin: 3.28 }, { hora: 7, promedioMin: 3.40 },
                { hora: 8, promedioMin: 3.52 }, { hora: 9, promedioMin: 3.38 }, { hora: 10, promedioMin: 3.62 },
                { hora: 11, promedioMin: 3.45 }, { hora: 12, promedioMin: 8.35 }, { hora: 13, promedioMin: 4.48 },
                { hora: 14, promedioMin: 3.58 }, { hora: 15, promedioMin: 3.82 }, { hora: 16, promedioMin: 3.50 },
                { hora: 17, promedioMin: 3.68 }, { hora: 18, promedioMin: 3.42 }, { hora: 19, promedioMin: 3.35 },
                { hora: 20, promedioMin: 3.72 }, { hora: 21, promedioMin: 3.48 }, { hora: 22, promedioMin: 3.22 }
            ] },
            { operador: "U10-US3", horas: [
                { hora: 5, promedioMin: 3.05 }, { hora: 6, promedioMin: 2.98 }, { hora: 7, promedioMin: 3.12 },
                { hora: 8, promedioMin: 3.25 }, { hora: 9, promedioMin: 3.15 }, { hora: 10, promedioMin: 3.38 },
                { hora: 11, promedioMin: 3.20 }, { hora: 12, promedioMin: 7.95 }, { hora: 13, promedioMin: 4.15 },
                { hora: 14, promedioMin: 3.32 }, { hora: 15, promedioMin: 3.60 }, { hora: 16, promedioMin: 3.28 },
                { hora: 17, promedioMin: 3.48 }, { hora: 18, promedioMin: 3.20 }, { hora: 19, promedioMin: 3.15 },
                { hora: 20, promedioMin: 3.50 }, { hora: 21, promedioMin: 3.28 }, { hora: 22, promedioMin: 3.00 }
            ] },
            { operador: "U12-US5", horas: [
                { hora: 5, promedioMin: 3.30 }, { hora: 6, promedioMin: 3.22 }, { hora: 7, promedioMin: 3.35 },
                { hora: 8, promedioMin: 3.45 }, { hora: 9, promedioMin: 3.32 }, { hora: 10, promedioMin: 3.55 },
                { hora: 11, promedioMin: 3.38 }, { hora: 12, promedioMin: 8.20 }, { hora: 13, promedioMin: 4.38 },
                { hora: 14, promedioMin: 3.50 }, { hora: 15, promedioMin: 3.75 }, { hora: 16, promedioMin: 3.42 },
                { hora: 17, promedioMin: 3.60 }, { hora: 18, promedioMin: 3.35 }, { hora: 19, promedioMin: 3.28 },
                { hora: 20, promedioMin: 3.65 }, { hora: 21, promedioMin: 3.40 }, { hora: 22, promedioMin: 3.15 }
            ] },
            { operador: "U19-US17", horas: [
                { hora: 5, promedioMin: 3.20 }, { hora: 6, promedioMin: 3.12 }, { hora: 7, promedioMin: 3.25 },
                { hora: 8, promedioMin: 3.38 }, { hora: 9, promedioMin: 3.28 }, { hora: 10, promedioMin: 3.50 },
                { hora: 11, promedioMin: 3.32 }, { hora: 12, promedioMin: 8.50 }, { hora: 13, promedioMin: 4.55 },
                { hora: 14, promedioMin: 3.62 }, { hora: 15, promedioMin: 3.88 }, { hora: 16, promedioMin: 3.58 },
                { hora: 17, promedioMin: 3.75 }, { hora: 18, promedioMin: 6.80 }, { hora: 19, promedioMin: 7.20 },
                { hora: 20, promedioMin: 6.95 }, { hora: 21, promedioMin: 6.40 }, { hora: 22, promedioMin: 6.10 }
            ] }
        ],

        top: [
            { amid: 7501500, zp: "RM-0995", nombre: "Parada 1 / (M) Zapadores", operador: "U19-US17", promedioMin: 359.8 },
            { amid: 7501112, zp: "RM-1025", nombre: "Parada 1 / (M) La Cisterna", operador: "U5-Metbus", promedioMin: 260.7 },
            { amid: 7518960, zp: "RM-1103", nombre: "Parada 1 / (M) Gruta de Lourdes", operador: "U8-US1", promedioMin: 251.7 },
            { amid: 7500934, zp: "RM-0765", nombre: "Parada 1 / (M) Escuela Militar", operador: "U12-US5", promedioMin: 241.9 },
            { amid: 7501051, zp: "RM-1157", nombre: "Parada 6 / (M) Francisco Bilbao", operador: "U5-Metbus", promedioMin: 203.2 },
            { amid: 7500942, zp: "RM-1150", nombre: "Parada 1 / (M) Macul", operador: "U10-US3", promedioMin: 42.4 },
            { amid: 7500763, zp: "RM-1193", nombre: "Parada 1 / (M) Departamental", operador: "U12-US5", promedioMin: 19.5 },
            { amid: 7501106, zp: "RM-0880", nombre: "Parada 4 / Las Parcelas", operador: "U1-Suburbus", promedioMin: 12.1 },
            { amid: 7501375, zp: "RM-0812", nombre: "Parada 1 / (M) Macul", operador: "U10-US3", promedioMin: 7.8 },
            { amid: 7501456, zp: "RM-0995", nombre: "Parada 1 / (M) Zapadores", operador: "U19-US17", promedioMin: 5.9 }
        ]
    },

    // ---------------------------------------------------------
    // Pestaña 3 · Dispositivos
    //
    // Las 48 filas del listado. El orden del arreglo NO importa:
    // el mock provider ordena según lo que pida la tabla.
    // ---------------------------------------------------------
    dispositivos: [
        { amid: 7501500, zp: "RM-0995", nombre: "Parada 1 / (M) Zapadores", operador: "U19-US17", trx: 217, promedioMin: 38.7, diasMalPortado: 13, enLab: true },
        { amid: 7501112, zp: "RM-1025", nombre: "Parada 1 / (M) La Cisterna", operador: "U5-Metbus", trx: 413, promedioMin: 31.2, diasMalPortado: 9, enLab: false },
        { amid: 7518960, zp: "RM-1103", nombre: "Parada 1 / (M) Gruta de Lourdes", operador: "U8-US1", trx: 497, promedioMin: 27.5, diasMalPortado: 7, enLab: false },
        { amid: 7500934, zp: "RM-0765", nombre: "Parada 1 / (M) Escuela Militar", operador: "U12-US5", trx: 245, promedioMin: 22.8, diasMalPortado: 11, enLab: false },
        { amid: 7501051, zp: "RM-1157", nombre: "Parada 6 / (M) Francisco Bilbao", operador: "U5-Metbus", trx: 417, promedioMin: 19.4, diasMalPortado: 6, enLab: false },
        { amid: 7500942, zp: "RM-1150", nombre: "Parada 1 / (M) Macul", operador: "U10-US3", trx: 232, promedioMin: 16.1, diasMalPortado: 11, enLab: true },
        { amid: 7500763, zp: "RM-1193", nombre: "Parada 1 / (M) Departamental", operador: "U12-US5", trx: 125, promedioMin: 19.5, diasMalPortado: 9, enLab: false },
        { amid: 7501106, zp: "RM-0880", nombre: "Parada 4 / Las Parcelas", operador: "U1-Suburbus", trx: 301, promedioMin: 12.1, diasMalPortado: 15, enLab: false },
        { amid: 7501375, zp: "RM-0812", nombre: "Parada 1 / (M) Macul", operador: "U10-US3", trx: 188, promedioMin: 7.8, diasMalPortado: 12, enLab: false },
        { amid: 7501456, zp: "RM-0995", nombre: "Parada 1 / (M) Zapadores", operador: "U19-US17", trx: 264, promedioMin: 5.9, diasMalPortado: 13, enLab: false },
        { amid: 7500851, zp: "RM-0901", nombre: "Parada 2 / (M) Lourdes", operador: "U2-Alsacia", trx: 142, promedioMin: 3.4, diasMalPortado: 0, enLab: false },
        { amid: 7500899, zp: "RM-0777", nombre: "Intermodal La Cisterna", operador: "U8-US1", trx: 389, promedioMin: 2.9, diasMalPortado: 0, enLab: false },

        { amid: 7501223, zp: "RM-0912", nombre: "Parada 2 / (M) San Miguel", operador: "U2-Alsacia", trx: 174, promedioMin: 5.6, diasMalPortado: 3, enLab: false },
        { amid: 7501338, zp: "RM-0844", nombre: "Parada 3 / (M) Los Trapenses", operador: "U1-Suburbus", trx: 198, promedioMin: 5.3, diasMalPortado: 2, enLab: false },
        { amid: 7501672, zp: "RM-1022", nombre: "Intermodal Lo Marcoleta", operador: "U1-Suburbus", trx: 355, promedioMin: 5.1, diasMalPortado: 1, enLab: false },
        { amid: 7501789, zp: "RM-0933", nombre: "Parada 4 / Las Parcelas", operador: "U1-Suburbus", trx: 288, promedioMin: 4.8, diasMalPortado: 4, enLab: false },
        { amid: 7502014, zp: "RM-1067", nombre: "Parada 1 / (M) San Joaquín", operador: "U19-US17", trx: 241, promedioMin: 4.1, diasMalPortado: 2, enLab: false },
        { amid: 7502145, zp: "RM-0788", nombre: "Parada 5 / (M) Quilicura", operador: "U19-US17", trx: 206, promedioMin: 4.0, diasMalPortado: 3, enLab: false },
        { amid: 7502287, zp: "RM-1131", nombre: "Parada 2 / (M) Carlos Valdovinos", operador: "U2-Alsacia", trx: 158, promedioMin: 3.8, diasMalPortado: 1, enLab: false },
        { amid: 7502412, zp: "RM-0956", nombre: "Parada 1 / (M) Zapadores", operador: "U19-US17", trx: 219, promedioMin: 3.7, diasMalPortado: 5, enLab: false },
        { amid: 7502533, zp: "RM-0888", nombre: "Parada 6 / (M) Pedro Aguirre", operador: "U5-Metbus", trx: 391, promedioMin: 3.6, diasMalPortado: 2, enLab: false },
        { amid: 7502674, zp: "RM-1043", nombre: "Parada 3 / (M) Ñuñoa", operador: "U5-Metbus", trx: 367, promedioMin: 3.5, diasMalPortado: 1, enLab: false },
        { amid: 7502791, zp: "RM-0799", nombre: "Parada 1 / (M) Guardia Vieja", operador: "U8-US1", trx: 344, promedioMin: 3.4, diasMalPortado: 2, enLab: false },
        { amid: 7502836, zp: "RM-1118", nombre: "Intermodal Vespucio", operador: "U8-US1", trx: 402, promedioMin: 3.3, diasMalPortado: 0, enLab: false },
        { amid: 7502954, zp: "RM-0867", nombre: "Parada 4 / Las Parcelas", operador: "U10-US3", trx: 276, promedioMin: 3.2, diasMalPortado: 3, enLab: false },
        { amid: 7503071, zp: "RM-1145", nombre: "Parada 5 / (M) Lo Prado", operador: "U10-US3", trx: 229, promedioMin: 3.1, diasMalPortado: 1, enLab: false },
        { amid: 7503188, zp: "RM-0944", nombre: "Parada 2 / (M) Cristales", operador: "U12-US5", trx: 171, promedioMin: 3.0, diasMalPortado: 2, enLab: false },
        { amid: 7503210, zp: "RM-1017", nombre: "Parada 6 / (M) Francisco Bilbao", operador: "U12-US5", trx: 424, promedioMin: 2.9, diasMalPortado: 0, enLab: false },
        { amid: 7503345, zp: "RM-0821", nombre: "Parada 1 / (M) Macul", operador: "U10-US3", trx: 195, promedioMin: 2.8, diasMalPortado: 4, enLab: false },
        { amid: 7503467, zp: "RM-0993", nombre: "Parada 3 / (M) Tobalaba", operador: "U1-Suburbus", trx: 183, promedioMin: 2.7, diasMalPortado: 1, enLab: false },
        { amid: 7503589, zp: "RM-1174", nombre: "Parada 5 / (M) El Salto", operador: "U19-US17", trx: 212, promedioMin: 2.6, diasMalPortado: 2, enLab: false },
        { amid: 7503702, zp: "RM-0905", nombre: "Parada 1 / (M) La Cisterna", operador: "U5-Metbus", trx: 408, promedioMin: 2.5, diasMalPortado: 1, enLab: false },
        { amid: 7503814, zp: "RM-1062", nombre: "Intermodal Maipú", operador: "U1-Suburbus", trx: 362, promedioMin: 2.4, diasMalPortado: 0, enLab: false },
        { amid: 7503927, zp: "RM-0839", nombre: "Parada 4 / Las Parcelas", operador: "U2-Alsacia", trx: 164, promedioMin: 2.3, diasMalPortado: 3, enLab: false },
        { amid: 7504038, zp: "RM-1129", nombre: "Parada 2 / (M) Santa Isabel", operador: "U8-US1", trx: 338, promedioMin: 2.2, diasMalPortado: 1, enLab: false },
        { amid: 7504151, zp: "RM-0958", nombre: "Parada 6 / (M) Conchalí", operador: "U5-Metbus", trx: 419, promedioMin: 2.1, diasMalPortado: 2, enLab: false },
        { amid: 7504263, zp: "RM-0876", nombre: "Parada 3 / (M) Departamental", operador: "U12-US5", trx: 133, promedioMin: 2.0, diasMalPortado: 1, enLab: false },
        { amid: 7504379, zp: "RM-1013", nombre: "Parada 1 / (M) Escuela Militar", operador: "U12-US5", trx: 248, promedioMin: 1.9, diasMalPortado: 0, enLab: false },
        { amid: 7504482, zp: "RM-1109", nombre: "Parada 5 / (M) Pudahuel", operador: "U10-US3", trx: 233, promedioMin: 1.8, diasMalPortado: 2, enLab: false },
        { amid: 7504596, zp: "RM-0948", nombre: "Parada 1 / (M) Zapadores", operador: "U19-US17", trx: 221, promedioMin: 1.7, diasMalPortado: 1, enLab: false },
        { amid: 7504608, zp: "RM-1166", nombre: "Parada 2 / (M) Lo Prado", operador: "U19-US17", trx: 187, promedioMin: 1.6, diasMalPortado: 0, enLab: false },
        { amid: 7504715, zp: "RM-0803", nombre: "Parada 3 / (M) Los Ríos", operador: "U1-Suburbus", trx: 176, promedioMin: 1.5, diasMalPortado: 3, enLab: false },
        { amid: 7504826, zp: "RM-1029", nombre: "Intermodal El Llano", operador: "U2-Alsacia", trx: 347, promedioMin: 1.4, diasMalPortado: 1, enLab: false },
        { amid: 7504939, zp: "RM-0917", nombre: "Parada 6 / (M) Vicuña Mackenna", operador: "U8-US1", trx: 451, promedioMin: 1.3, diasMalPortado: 0, enLab: false },
        { amid: 7505041, zp: "RM-1055", nombre: "Parada 4 / Las Parcelas", operador: "U5-Metbus", trx: 298, promedioMin: 1.2, diasMalPortado: 2, enLab: false },
        { amid: 7505153, zp: "RM-1136", nombre: "Parada 1 / (M) Zapadores", operador: "U19-US17", trx: 225, promedioMin: 1.1, diasMalPortado: 1, enLab: false },
        { amid: 7505267, zp: "RM-0982", nombre: "Parada 5 / (M) Cerrillos", operador: "U10-US3", trx: 216, promedioMin: 1.0, diasMalPortado: 0, enLab: false },
        { amid: 7505374, zp: "RM-1071", nombre: "Parada 3 / (M) Ñuñoa", operador: "U12-US5", trx: 372, promedioMin: 0.9, diasMalPortado: 1, enLab: false }
    ],

    // Ficha de cualquier validador. La serie por hora es la misma
    // que la del resumen diario, tal como pide la especificación.
    ficha: {
        porHora: [
            { hora: 5, promedioMin: 3.20 }, { hora: 6, promedioMin: 3.15 }, { hora: 7, promedioMin: 3.17 },
            { hora: 8, promedioMin: 3.24 }, { hora: 9, promedioMin: 3.28 }, { hora: 10, promedioMin: 3.46 },
            { hora: 11, promedioMin: 3.32 }, { hora: 12, promedioMin: 8.15 }, { hora: 13, promedioMin: 5.01 },
            { hora: 14, promedioMin: 3.57 }, { hora: 15, promedioMin: 4.04 }, { hora: 16, promedioMin: 3.57 },
            { hora: 17, promedioMin: 4.02 }, { hora: 18, promedioMin: 3.37 }, { hora: 19, promedioMin: 3.38 },
            { hora: 20, promedioMin: 4.18 }, { hora: 21, promedioMin: 3.35 }, { hora: 22, promedioMin: 3.10 }
        ],

        ultimos30dias: [
            { fecha: "2026-07-29", promedioMin: 4.12 }, { fecha: "2026-07-30", promedioMin: 3.85 },
            { fecha: "2026-07-31", promedioMin: 4.40 }, { fecha: "2026-08-01", promedioMin: 3.63 },
            { fecha: "2026-08-02", promedioMin: 3.67 }, { fecha: "2026-08-03", promedioMin: 3.75 },
            { fecha: "2026-08-04", promedioMin: 3.66 }, { fecha: "2026-08-05", promedioMin: 3.70 },
            { fecha: "2026-08-06", promedioMin: 3.73 }, { fecha: "2026-08-07", promedioMin: 3.70 },
            { fecha: "2026-08-08", promedioMin: 3.63 }, { fecha: "2026-08-09", promedioMin: 3.67 },
            { fecha: "2026-08-10", promedioMin: 3.67 }, { fecha: "2026-08-11", promedioMin: 3.67 },
            { fecha: "2026-08-12", promedioMin: 3.73 }, { fecha: "2026-08-13", promedioMin: 3.73 },
            { fecha: "2026-08-14", promedioMin: 3.69 }, { fecha: "2026-08-15", promedioMin: 3.64 },
            { fecha: "2026-08-16", promedioMin: 3.78 }, { fecha: "2026-08-17", promedioMin: 3.68 },
            { fecha: "2026-08-18", promedioMin: 3.68 }, { fecha: "2026-08-19", promedioMin: 3.65 },
            { fecha: "2026-08-20", promedioMin: 3.68 }, { fecha: "2026-08-21", promedioMin: 3.68 },
            { fecha: "2026-08-22", promedioMin: 6.83 }, { fecha: "2026-08-23", promedioMin: 5.33 },
            { fecha: "2026-08-24", promedioMin: 4.97 }, { fecha: "2026-08-25", promedioMin: 3.65 },
            { fecha: "2026-08-26", promedioMin: 3.67 }, { fecha: "2026-08-27", promedioMin: 3.67 }
        ],

        laboratorio: [
            { fecha: "2026-08-20", situacion: "Canal principal (Claro): falla de transmisión", accion: "Cambio de antenas" },
            { fecha: "2026-08-18", situacion: "Falla de transmisión hacia servidor", accion: "Ajustes y limpieza" }
        ]
    },

    // ---------------------------------------------------------
    // Pestaña 4 · Rezagadas
    // ---------------------------------------------------------
    rezagadas: {
        total: 8473,
        mayorDia: { fecha: "2026-08-24", trx: 1026 },
        dispositivos: 312,
        porDiaLlegada: [
            { fecha: "2026-08-03", trx: 334 },
            { fecha: "2026-08-04", trx: 290 },
            { fecha: "2026-08-05", trx: 218 },
            { fecha: "2026-08-06", trx: 472 },
            { fecha: "2026-08-07", trx: 889 },
            { fecha: "2026-08-10", trx: 631 },
            { fecha: "2026-08-11", trx: 627 },
            { fecha: "2026-08-12", trx: 931 },
            { fecha: "2026-08-13", trx: 475 },
            { fecha: "2026-08-14", trx: 333 },
            { fecha: "2026-08-17", trx: 433 },
            { fecha: "2026-08-18", trx: 510 },
            { fecha: "2026-08-19", trx: 325 },
            { fecha: "2026-08-20", trx: 433 },
            { fecha: "2026-08-21", trx: 97 },
            { fecha: "2026-08-24", trx: 1026 },
            { fecha: "2026-08-25", trx: 173 },
            { fecha: "2026-08-26", trx: 88 },
            { fecha: "2026-08-27", trx: 188 }
        ]
    }
};