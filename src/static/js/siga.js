/* SIGA · Comportamiento común a todas las páginas */
document.addEventListener('DOMContentLoaded', function () {
  // Íconos Lucide: reemplaza cada <i data-lucide="..."> por su SVG
  if (window.lucide) lucide.createIcons();

  // Menú lateral en pantallas chicas
  var app = document.querySelector('.app');
  var menuBtn = document.querySelector('.menu-btn');
  if (app && menuBtn) {
    menuBtn.addEventListener('click', function () { app.classList.toggle('nav-open'); });
  }

  // Botones que abren un <dialog>: <button data-abrir="id-del-dialogo">
  document.querySelectorAll('[data-abrir]').forEach(function (boton) {
    boton.addEventListener('click', function () {
      document.getElementById(boton.dataset.abrir).showModal();
    });
  });
  // Botones que cierran el <dialog> donde están
  document.querySelectorAll('[data-cerrar]').forEach(function (boton) {
    boton.addEventListener('click', function () { boton.closest('dialog').close(); });
  });

  // Tarjeta del período: se minimiza y el navegador lo recuerda
  var periodo = document.getElementById('periodo-card');
  if (periodo) {
    var cabecera = periodo.querySelector('.periodo-head');
    var CLAVE = 'siga.periodoMinimizado';
    var aplicar = function (minimizada) {
      periodo.classList.toggle('minimizada', minimizada);
      cabecera.setAttribute('aria-expanded', String(!minimizada));
    };
    try { aplicar(localStorage.getItem(CLAVE) === '1'); } catch (e) { /* sin almacenamiento: queda abierta */ }
    cabecera.addEventListener('click', function () {
      var minimizada = !periodo.classList.contains('minimizada');
      aplicar(minimizada);
      try { localStorage.setItem(CLAVE, minimizada ? '1' : '0'); } catch (e) { /* no importa */ }
    });
  }

  // Mensajes de Django (messages) como aviso flotante que se oculta solo
  document.querySelectorAll('.toast').forEach(function (toast) {
    requestAnimationFrame(function () { toast.classList.add('show'); });
    setTimeout(function () { toast.classList.remove('show'); }, 4500);
  });
});
