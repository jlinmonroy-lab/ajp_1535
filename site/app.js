/* Frontend de AJP en directo.
 *
 * Sin dependencias ni build: descarga data.json, lo guarda en memoria y pinta.
 * El polling usa ETag, así que un ciclo sin cambios no descarga nada.
 */
'use strict';

const REFRESCO_MS = 30000;
const CLAVE_SEGUIDOS = 'ajp:seguidos';
const MEDALLAS = { gold: '🥇', silver: '🥈', bronze: '🥉' };

let datos = null;
let etag = null;
let porId = new Map();      // id de combate -> combate
let vista = 'seguidos';

/* ---------- Almacenamiento local ----------
   Puede fallar (modo privado, cookies bloqueadas) y la app debe seguir
   funcionando sin ello, así que todo acceso va envuelto. */
function leerSeguidos() {
  try {
    return new Set(JSON.parse(localStorage.getItem(CLAVE_SEGUIDOS)) || []);
  } catch {
    return new Set();
  }
}
function guardarSeguidos(conjunto) {
  try {
    localStorage.setItem(CLAVE_SEGUIDOS, JSON.stringify([...conjunto]));
  } catch { /* sin persistencia, pero la sesión sigue */ }
}
let seguidos = leerSeguidos();

/* ---------- Utilidades ---------- */
const $ = (sel) => document.querySelector(sel);

// Buscar "muñoz" debe encontrar "Muñoz", y "jose" debe encontrar "José".
const normalizar = (texto) => (texto || '')
  .toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

function escapar(texto) {
  const d = document.createElement('div');
  d.textContent = texto == null ? '' : String(texto);
  return d.innerHTML;
}

function hora(iso) {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return isNaN(d) ? '--:--'
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function hace(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  if (s < 60) return `hace ${Math.floor(s)}s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  return `hace ${Math.floor(s / 3600)} h`;
}

/* ---------- Carga ---------- */
async function cargar() {
  try {
    const cabeceras = etag ? { 'If-None-Match': etag } : {};
    const resp = await fetch('data.json', { cache: 'no-store', headers: cabeceras });

    if (resp.status === 304) { pintarEstado(); return; }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    etag = resp.headers.get('ETag');
    datos = await resp.json();
    porId = new Map(datos.matches.map((m) => [m.id, m]));

    if (datos.event?.name) {
      $('#nombre-evento').textContent = datos.event.name;
      document.title = datos.event.name;
    }
    pintar();
  } catch (e) {
    const estado = $('#estado');
    estado.textContent = `Sin conexión con los datos (${e.message})`;
    estado.classList.add('vieja');
  }
}

function pintarEstado() {
  if (!datos) return;
  const estado = $('#estado');
  const total = `${datos.matches.length} combates · ${datos.athletes.length} atletas`;
  if (datos.stale) {
    estado.textContent = `⚠ Datos sin actualizar desde ${hora(datos.staleSince)} · ${total}`;
    estado.classList.add('vieja');
  } else {
    estado.textContent = `Actualizado ${hace(datos.fetchedAt)} · ${total}`;
    estado.classList.remove('vieja');
  }
}

/* ---------- Combates ---------- */
function combatesDe(atleta) {
  return atleta.matchIds.map((id) => porId.get(id)).filter(Boolean);
}

function rivalDe(combate, registrationId) {
  return combate.sides.find((s) => s.registrationId !== registrationId) || null;
}

function etiquetaResultado(combate, registrationId) {
  if (combate.state === 'running') return '<span class="etiqueta vivo">EN CURSO</span>';
  if (combate.state !== 'finished') return '<span class="etiqueta">Pendiente</span>';

  const yo = combate.sides.find((s) => s.registrationId === registrationId);
  if (!yo) return '<span class="etiqueta">Terminado</span>';
  const clase = yo.isWinner ? 'ganado' : 'perdido';
  const texto = yo.isWinner ? 'Ganó' : 'Perdió';
  const modo = combate.wonBy ? ` · ${combate.wonBy}` : '';
  return `<span class="etiqueta ${clase}">${texto}${escapar(modo)}</span>`;
}

function filaCombate(combate, registrationId) {
  const rival = rivalDe(combate, registrationId);
  const nombreRival = rival ? rival.name : 'Por determinar';
  const ronda = combate.round ? `${escapar(combate.round)} · ` : '';
  return `
    <div class="combate">
      <span class="hora">${hora(combate.estimatedStart)}</span>
      <span class="detalle-combate">
        <span class="rival">vs ${escapar(nombreRival)}</span><br>
        <span class="sub">${ronda}${escapar(combate.mat || '')}</span>
      </span>
      ${etiquetaResultado(combate, registrationId)}
    </div>`;
}

/* ---------- Vistas ---------- */
function tarjetaAtleta(atleta, { conCombates = false } = {}) {
  const sigue = seguidos.has(atleta.registrationId);
  const medalla = atleta.bestMedal
    ? `<span class="medalla" data-m="${atleta.bestMedal}">${MEDALLAS[atleta.bestMedal]}</span>` : '';
  const foto = atleta.image
    ? `<img class="foto" src="${escapar(atleta.image)}" alt="" loading="lazy">`
    : '<span class="foto"></span>';

  let combates = '';
  if (conCombates) {
    const lista = combatesDe(atleta);
    combates = lista.length
      ? lista.map((c) => filaCombate(c, atleta.registrationId)).join('')
      : '<p class="sub">Sin combates en el schedule todavía.</p>';
  }

  return `
    <article class="tarjeta">
      <div class="tarjeta-cabecera">
        ${foto}
        <span class="crece" data-atleta="${escapar(atleta.registrationId)}">
          <span class="nombre">${escapar(atleta.name)} ${medalla}</span><br>
          <span class="sub">${escapar(atleta.club || '—')} · ${escapar(atleta.categories[0] || '')}</span>
        </span>
        <button class="seguir ${sigue ? 'activo' : ''}"
                data-seguir="${escapar(atleta.registrationId)}">${sigue ? 'Siguiendo' : 'Seguir'}</button>
      </div>
      ${combates}
    </article>`;
}

function pintarSeguidos() {
  const caja = $('#vista-seguidos');
  $('#contador-seguidos').textContent = seguidos.size || '';

  if (!seguidos.size) {
    caja.innerHTML = `<p class="vacio">Todavía no sigues a nadie.<br>
      Usa <strong>Buscar</strong> para añadir atletas y sus combates aparecerán aquí.</p>`;
    return;
  }

  const mios = datos.athletes.filter((a) => seguidos.has(a.registrationId));
  if (!mios.length) {
    caja.innerHTML = `<p class="vacio">Tus atletas no aparecen en este evento.</p>`;
    return;
  }

  // Lo primero que quiere ver alguien en el pabellón: qué toca ahora y qué viene.
  const proximos = [];
  for (const a of mios) {
    for (const c of combatesDe(a)) {
      if (c.state !== 'finished') proximos.push({ atleta: a, combate: c });
    }
  }
  proximos.sort((x, y) => (x.combate.estimatedStart || '').localeCompare(y.combate.estimatedStart || ''));

  let html = '';
  if (proximos.length) {
    html += '<h2 class="seccion-titulo">Próximos combates</h2>';
    html += proximos.slice(0, 8).map(({ atleta, combate }) => `
      <article class="tarjeta">
        <div class="tarjeta-cabecera">
          <span class="hora">${hora(combate.estimatedStart)}</span>
          <span class="crece">
            <span class="nombre">${escapar(atleta.name)}</span><br>
            <span class="sub">vs ${escapar((rivalDe(combate, atleta.registrationId) || {}).name || 'Por determinar')}
              · ${escapar(combate.mat || '')}</span>
          </span>
          ${etiquetaResultado(combate, atleta.registrationId)}
        </div>
      </article>`).join('');
  }

  html += '<h2 class="seccion-titulo">Mis atletas</h2>';
  html += mios.map((a) => tarjetaAtleta(a, { conCombates: true })).join('');
  caja.innerHTML = html;
}

function pintarBusqueda() {
  const consulta = normalizar($('#busqueda').value.trim());
  const caja = $('#resultados');

  if (consulta.length < 2) {
    caja.innerHTML = '<p class="vacio">Escribe al menos dos letras.</p>';
    return;
  }

  const encontrados = datos.athletes.filter((a) =>
    normalizar(a.name).includes(consulta) ||
    normalizar(a.club).includes(consulta) ||
    a.categories.some((c) => normalizar(c).includes(consulta)));

  caja.innerHTML = encontrados.length
    ? `<p class="sub">${encontrados.length} resultado(s)</p>` +
      encontrados.slice(0, 60).map((a) => tarjetaAtleta(a)).join('')
    : '<p class="vacio">Ningún atleta coincide.</p>';
}

function pintarTatamis() {
  const caja = $('#vista-tatamis');
  const porMat = new Map(datos.mats.map((m) => [m.name, []]));
  for (const c of datos.matches) {
    if (porMat.has(c.mat)) porMat.get(c.mat).push(c);
  }

  const streams = new Map((datos.streams || []).map((s) => [s.mat, s.url]));

  caja.innerHTML = datos.mats.map((mat) => {
    const combates = porMat.get(mat.name) || [];
    const enCurso = combates.filter((c) => c.state === 'running');
    const siguientes = combates.filter((c) => c.state !== 'finished' && c.state !== 'running');
    const mostrar = [...enCurso, ...siguientes].slice(0, 5);
    const url = streams.get(mat.name);

    return `
      <article class="tarjeta">
        <div class="tarjeta-cabecera">
          <span class="crece">
            <span class="nombre">${escapar(mat.name)}</span><br>
            <span class="sub">${combates.length} combates · ${enCurso.length} en curso</span>
          </span>
        </div>
        ${mostrar.length
          ? mostrar.map((c) => `
            <div class="combate">
              <span class="hora">${hora(c.estimatedStart)}</span>
              <span class="detalle-combate">
                <span class="rival">${escapar(c.sides.map((s) => s.name).join(' vs ') || 'Por determinar')}</span><br>
                <span class="sub">${escapar(c.category.raw || '')}</span>
              </span>
              ${c.state === 'running' ? '<span class="etiqueta vivo">EN CURSO</span>' : ''}
            </div>`).join('')
          : '<p class="sub">Sin combates pendientes.</p>'}
        ${url ? `<a class="enlace-stream" href="${escapar(url)}" target="_blank" rel="noopener">Ver retransmisión ↗</a>` : ''}
      </article>`;
  }).join('');
}

function pintar() {
  if (!datos) return;
  pintarEstado();
  if (vista === 'seguidos') pintarSeguidos();
  else if (vista === 'buscar') pintarBusqueda();
  else pintarTatamis();
}

/* ---------- Detalle de atleta ---------- */
function abrirDetalle(registrationId) {
  const atleta = datos.athletes.find((a) => a.registrationId === registrationId);
  if (!atleta) return;

  $('#detalle-nombre').textContent = atleta.name;
  const medallas = atleta.medals.length
    ? `<p class="sub">${atleta.medals.map((m) =>
        `${MEDALLAS[m.medal]} ${escapar(m.category || '')}`).join('<br>')}</p>`
    : '';
  $('#detalle-cuerpo').innerHTML = `
    <p class="sub">${escapar(atleta.club || '—')}${atleta.country ? ' · ' + escapar(atleta.country) : ''}</p>
    ${medallas}
    <h3 class="seccion-titulo">Combates</h3>
    ${combatesDe(atleta).map((c) => filaCombate(c, atleta.registrationId)).join('') || '<p class="sub">Sin combates.</p>'}`;
  $('#detalle').classList.remove('oculta');
}

/* ---------- Eventos ---------- */
document.querySelectorAll('.pestana').forEach((boton) => {
  boton.addEventListener('click', () => {
    document.querySelectorAll('.pestana').forEach((b) => {
      b.classList.remove('activa');
      b.setAttribute('aria-selected', 'false');
    });
    boton.classList.add('activa');
    boton.setAttribute('aria-selected', 'true');
    vista = boton.dataset.vista;
    document.querySelectorAll('.vista').forEach((v) => v.classList.add('oculta'));
    $(`#vista-${vista}`).classList.remove('oculta');
    pintar();
    if (vista === 'buscar') $('#busqueda').focus();
  });
});

// Delegación: las tarjetas se repintan enteras en cada ciclo, así que no sirve
// enganchar escuchadores a cada botón.
document.addEventListener('click', (ev) => {
  const seguir = ev.target.closest('[data-seguir]');
  if (seguir) {
    const id = seguir.dataset.seguir;
    if (seguidos.has(id)) seguidos.delete(id); else seguidos.add(id);
    guardarSeguidos(seguidos);
    pintar();
    return;
  }
  const abrir = ev.target.closest('[data-atleta]');
  if (abrir) abrirDetalle(abrir.dataset.atleta);
});

$('#cerrar-detalle').addEventListener('click', () => $('#detalle').classList.add('oculta'));
$('#detalle').addEventListener('click', (ev) => {
  if (ev.target.id === 'detalle') $('#detalle').classList.add('oculta');
});
$('#busqueda').addEventListener('input', pintarBusqueda);
$('#recargar').addEventListener('click', () => { etag = null; cargar(); });

/* ---------- Arranque ---------- */
cargar();
setInterval(cargar, REFRESCO_MS);
// El "hace X" envejece aunque no lleguen datos nuevos.
setInterval(pintarEstado, 10000);
