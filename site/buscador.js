/* Pantalla de inicio: buscar un evento de Smoothcomp.
 *
 * Habla con /api/events/search, que el servidor contesta de su caché (nunca
 * con una lectura de Smoothcomp en medio), y lleva a #/evento/ID. Los eventos
 * que se abren se recuerdan en este navegador para volver a ellos de un toque.
 */
'use strict';

const CLAVE_RECIENTES = 'sbjj:recientes';
const MAX_RECIENTES = 8;
const ESPERA_ESCRITURA_MS = 350;

const Inicio = (() => {
  const est = {
    q: '', cuando: 'upcoming', pagina: 1,
    eventos: [], hayMas: false, vieja: false,
    cargando: false, error: null,
    ticket: 0,        // descarta respuestas de búsquedas que ya no son la última
    iniciado: false,
    // La zona por defecto de config.json ("Madrid, España"). `zona` es su nombre, o
    // null si no hay; `zonaActiva`, si el chip está encendido. Empieza encendido en
    // cada visita: no se recuerda que alguien lo apagara.
    zona: null, zonaActiva: false,
  };
  let temporizador = null;

  /* ---------- Lo que se escribe puede ser un enlace o un número ---------- */
  // Pegar https://spainbjjtour.smoothcomp.com/es/event/33588 o escribir 33588 ofrece
  // abrir ese evento directamente: es la salida si la búsqueda no está disponible.
  function idDeEvento(texto) {
    const t = (texto || '').trim();
    const enlace = t.match(/smoothcomp\.com\/[^\s?#]*?\/event\/(\d{1,9})/i);
    if (enlace) return String(Number(enlace[1]));
    if (/^\d{1,9}(\s*,\s*\d{1,9}){0,2}$/.test(t)) {
      return t.split(',').map((n) => String(Number(n))).join(',');
    }
    return null;
  }

  /* ---------- Recientes ---------- */
  function recientes() {
    return leerLocal(CLAVE_RECIENTES, []).filter((r) => r && r.id && r.title);
  }

  // Lo llama app.js al cargar un evento: así "Recientes" nunca guarda ids que no existen.
  function recordar(evento) {
    const lista = recientes().filter((r) => r.id !== evento.id);
    lista.unshift({
      id: evento.id, title: evento.title,
      startdate: evento.startdate || null, enddate: evento.enddate || null,
      city: evento.city || null, country: evento.country || null,
    });
    guardarLocal(CLAVE_RECIENTES, lista.slice(0, MAX_RECIENTES));
  }

  /* ---------- Pintado ---------- */
  function hoy() {
    return new Date().toLocaleDateString('sv-SE');   // YYYY-MM-DD en hora local
  }

  function chipDelEvento(e) {
    const fin = e.enddate || e.startdate;
    if (e.ended || (fin && fin < hoy())) return '<span class="etiqueta">Finalizado</span>';
    if (e.startdate && e.startdate <= hoy()) {
      // Las ligas y circuitos duran meses: "Hoy" solo si de verdad empieza hoy.
      return `<span class="etiqueta vivo">${e.startdate === hoy() ? 'Hoy' : 'En curso'}</span>`;
    }
    return '';
  }

  function tarjetaEvento(e) {
    const lugar = [e.city, e.country].filter(Boolean).join(', ');
    const detalle = [rangoFechas(e.startdate, e.enddate), lugar].filter(Boolean).join(' · ');
    return `
      <a class="tarjeta evento" href="#/evento/${escapar(e.id)}">
        <span class="crece">
          <span class="nombre">${escapar(e.title)}</span>
          <span class="sub">${escapar(detalle || 'Sin fecha')}</span>
        </span>
        ${chipDelEvento(e)}
      </a>`;
  }

  function tarjetaAbrirPorId(id) {
    return `
      <a class="tarjeta evento abrir-id" href="#/evento/${escapar(id)}">
        <span class="crece">
          <span class="nombre">Abrir el evento n.º ${escapar(id.replace(/,/g, ', '))}</span>
          <span class="sub">Directamente, sin buscar</span>
        </span>
        <span class="etiqueta">Abrir</span>
      </a>`;
  }

  const TITULO_RESULTADOS = {
    upcoming: 'Próximos eventos', past: 'Eventos pasados', all: 'Eventos',
  };

  // El chip de la zona: encendido filtra, apagado se queda a la vista para volver a encenderlo.
  function pintarChip() {
    const chip = $('#zona');
    chip.classList.toggle('oculta', !est.zona);
    chip.classList.toggle('activo', est.zonaActiva);
    chip.setAttribute('aria-pressed', String(est.zonaActiva));
    chip.textContent = est.zona ? `📍 ${est.zona}${est.zonaActiva ? ' ✕' : ''}` : '';
  }

  function pintar() {
    const id = idDeEvento(est.q);
    const guardados = recientes();
    const lugar = est.zonaActiva ? ` en ${est.zona}` : '';

    $('#recientes').innerHTML = (!est.q && guardados.length)
      ? `<h2 class="seccion-titulo">Recientes</h2>${guardados.map(tarjetaEvento).join('')}`
      : '';

    let html = id ? tarjetaAbrirPorId(id) : '';
    const hayResultados = est.eventos.length > 0;

    if (hayResultados) {
      html += `<h2 class="seccion-titulo">${
        est.q ? 'Resultados' : TITULO_RESULTADOS[est.cuando]}${escapar(lugar)}</h2>`;
      if (est.vieja) {
        html += '<p class="sub">Smoothcomp no responde ahora: se muestran resultados guardados.</p>';
      }
      html += est.eventos.map(tarjetaEvento).join('');
    }

    if (est.error) {
      html += `<p class="vacio error">${escapar(est.error)}<br>
        <button type="button" class="seguir" data-reintentar>Reintentar</button></p>`;
    } else if (est.cargando && !hayResultados) {
      html += '<p class="vacio">Buscando…</p>';
    } else if (!est.cargando && !hayResultados && !id) {
      // Con la zona encendida, lo que no sale puede estar fuera de ella: se ofrece salir.
      const salir = est.zonaActiva
        ? `<br><button type="button" class="seguir" data-sin-zona>Buscar en todo el mundo</button>`
        : '';
      html += est.q
        ? `<p class="vacio">Ningún evento${escapar(lugar)} coincide con «${escapar(est.q)}».${
            est.cuando === 'upcoming' ? '<br>Prueba también en <strong>Pasados</strong>.' : ''}${salir}</p>`
        : `<p class="vacio">No hay ${est.cuando === 'upcoming' ? 'próximos ' : ''}eventos${
            escapar(lugar)}.${salir}</p>`;
    }

    $('#resultados-eventos').innerHTML = html;

    const mas = $('#mas-eventos');
    mas.classList.toggle('oculta', !(est.hayMas && hayResultados && !est.error));
    mas.disabled = est.cargando;
    mas.textContent = est.cargando ? 'Cargando…' : 'Cargar más';
  }

  /* ---------- Búsqueda ---------- */
  async function buscar(reiniciar) {
    const ticket = ++est.ticket;
    if (reiniciar) {
      est.pagina = 1;
      est.eventos = [];
      est.hayMas = false;
      est.vieja = false;
    } else {
      est.pagina += 1;
    }
    est.error = null;
    est.cargando = true;
    pintar();

    const params = new URLSearchParams({ q: est.q, when: est.cuando, page: String(est.pagina) });
    if (est.zonaActiva) params.set('zona', '1');
    try {
      const resp = await fetch(`api/events/search?${params}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(await mensajeDeError(resp));
      const cuerpo = await resp.json();
      if (ticket !== est.ticket) return;

      const vistos = new Set(est.eventos.map((e) => e.id));
      est.eventos = est.eventos.concat(cuerpo.events.filter((e) => !vistos.has(e.id)));
      est.hayMas = !!cuerpo.hasMore;
      est.vieja = !!cuerpo.stale;
    } catch (e) {
      if (ticket !== est.ticket) return;
      est.error = e.message || 'No se pudo buscar';
      if (!reiniciar) est.pagina -= 1;
    } finally {
      if (ticket === est.ticket) {
        est.cargando = false;
        pintar();
      }
    }
  }

  /* ---------- Arranque ---------- */
  function iniciar() {
    est.iniciado = true;

    $('#busqueda-eventos').addEventListener('input', (ev) => {
      est.q = ev.target.value.trim();
      pintar();     // la tarjeta "Abrir el evento n.º…" aparece sin esperar
      clearTimeout(temporizador);
      temporizador = setTimeout(() => buscar(true), ESPERA_ESCRITURA_MS);
    });

    $('#form-eventos').addEventListener('submit', (ev) => {
      ev.preventDefault();
      clearTimeout(temporizador);
      buscar(true);
      $('#busqueda-eventos').blur();     // en el móvil, esconde el teclado
    });

    document.querySelectorAll('.filtro').forEach((boton) => {
      boton.addEventListener('click', () => {
        est.cuando = boton.dataset.cuando;
        document.querySelectorAll('.filtro').forEach((b) => {
          const activo = b === boton;
          b.classList.toggle('activo', activo);
          b.setAttribute('aria-pressed', String(activo));
        });
        clearTimeout(temporizador);
        buscar(true);
      });
    });

    $('#mas-eventos').addEventListener('click', () => buscar(false));
    $('#zona').addEventListener('click', () => cambiarZona(!est.zonaActiva));
    $('#resultados-eventos').addEventListener('click', (ev) => {
      if (ev.target.closest('[data-reintentar]')) buscar(est.pagina <= 1);
      if (ev.target.closest('[data-sin-zona]')) cambiarZona(false);
    });
  }

  function cambiarZona(activa) {
    est.zonaActiva = activa && !!est.zona;
    pintarChip();
    clearTimeout(temporizador);
    buscar(true);
  }

  // Lo llama app.js con la zona de /api/config (o null) antes de enseñar el inicio.
  function configurar(zona) {
    est.zona = zona && zona.nombre ? String(zona.nombre) : null;
    est.zonaActiva = !!est.zona;
    pintarChip();
  }

  // Se llama cada vez que se vuelve a la pantalla de inicio.
  function mostrar() {
    if (!est.iniciado) iniciar();
    if (!est.eventos.length && !est.cargando && !est.error) buscar(true);
    else pintar();    // los "Recientes" pueden haber cambiado
  }

  return { mostrar, recordar, configurar };
})();
