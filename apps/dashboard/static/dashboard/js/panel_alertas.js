document.addEventListener("DOMContentLoaded", function () {
    const btnSeleccionar = document.getElementById("btn-seleccionar-ubicaciones");
    const btnDeseleccionar = document.getElementById("btn-deseleccionar-ubicaciones");
    const checkboxes = document.querySelectorAll(".checkbox-ubicacion");

    if (btnSeleccionar) {
        btnSeleccionar.addEventListener("click", function () {
            checkboxes.forEach(function (checkbox) {
                checkbox.checked = true;
            });
        });
    }

    if (btnDeseleccionar) {
        btnDeseleccionar.addEventListener("click", function () {
            checkboxes.forEach(function (checkbox) {
                checkbox.checked = false;
            });
        });
    }
});