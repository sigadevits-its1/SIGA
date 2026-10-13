/*
 * SIGA · Formulario de preinscripción
 * Ayudas para el aspirante mientras completa el formulario.
 * La validación que vale es la del servidor (forms.py); esto sólo avisa antes.
 */
document.addEventListener('DOMContentLoaded', function () {
  var form = document.querySelector('form.preinscripcion');
  if (!form) return;

  // ---- Calendario de fecha de nacimiento (flatpickr, en español) ----
  var fecha = form.querySelector('[data-calendario]');
  if (fecha && window.flatpickr) {
    var hoy = new Date();
    flatpickr(fecha, {
      locale: 'es',
      dateFormat: 'Y-m-d',        // lo que se envía al servidor
      altInput: true,             // lo que ve la persona
      altFormat: 'd/m/Y',
      altInputClass: 'control',
      allowInput: true,           // también se puede escribir a mano
      maxDate: hoy,
      monthSelectorType: 'dropdown',
      // Abre en un año típico de ingresante para no navegar mes por mes
      onOpen: function (sel, valor, fp) {
        if (!valor) fp.jumpToDate(new Date(hoy.getFullYear() - 18, 0, 1));
      },
      onChange: function () { actualizarPasos(); }
    });
  }

  var MAX_BYTES = 10 * 1024 * 1024;
  var FORMATOS = /\.(pdf|jpe?g|png)$/i;

  // ---- Archivos: mostrar el nombre elegido y avisar formato o tamaño ----
  form.querySelectorAll('.file input[type=file]').forEach(function (input) {
    var fila = input.closest('.file');
    var detalle = fila.querySelector('small');
    var textoOriginal = detalle.textContent;

    input.addEventListener('change', function () {
      var archivo = input.files[0];
      fila.classList.remove('loaded', 'invalid');
      if (!archivo) { detalle.textContent = textoOriginal; return; }

      if (!FORMATOS.test(archivo.name)) {
        detalle.textContent = '“' + archivo.name + '” no es un formato válido. Usá PDF, JPG o PNG.';
        fila.classList.add('invalid');
        input.value = '';
      } else if (archivo.size > MAX_BYTES) {
        detalle.textContent = 'El archivo pesa ' + (archivo.size / 1048576).toFixed(1) + ' MB. El máximo es 10 MB.';
        fila.classList.add('invalid');
        input.value = '';
      } else {
        detalle.textContent = archivo.name + ' · ' + (archivo.size / 1048576).toFixed(1) + ' MB';
        fila.classList.add('loaded');
      }
      actualizarPasos();
    });
  });

  // ---- Título o constancia: cambia el texto de la fila del archivo ----
  var tituloNombre = document.getElementById('titulo-nombre');
  form.querySelectorAll('input[name=titulo_situacion]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      tituloNombre.textContent = radio.dataset.label;
    });
  });

  // ---- Pasos: marca los completos y el actual ----
  function completo(nombres) {
    return nombres.every(function (nombre) {
      var campo = form.elements[nombre];
      if (!campo) return true;
      if (campo instanceof RadioNodeList) return campo.value !== '';
      if (campo.type === 'checkbox' || campo.type === 'radio') return campo.checked;
      if (campo.type === 'file') return campo.files.length > 0;
      return campo.value.trim() !== '';
    });
  }

  var pasos = {
    personales: ['nombre', 'apellido', 'dni', 'fecha_nacimiento', 'email', 'email_confirmacion', 'telefono'],
    carrera: ['oferta'],
    docs: ['archivo_dni', 'archivo_titulo'],
    envio: ['declaracion', 'privacidad']
  };

  function actualizarPasos() {
    var actualMarcado = false;
    document.querySelectorAll('.steps li[data-step]').forEach(function (li, i) {
      var ok = completo(pasos[li.dataset.step]);
      var esActual = !ok && !actualMarcado;
      if (esActual) actualMarcado = true;
      li.classList.toggle('done', ok);
      li.classList.toggle('current', esActual);
      li.querySelector('.dot').innerHTML = ok ? '<i data-lucide="check"></i>' : String(i + 1);
    });
    if (window.lucide) lucide.createIcons();
  }

  form.addEventListener('input', actualizarPasos);
  form.addEventListener('change', actualizarPasos);
  actualizarPasos();
});
