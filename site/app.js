/* Frontend de AJP en directo.
 *
 * Sin dependencias ni build: descarga data.json, lo guarda en memoria y pinta.
 * El polling usa ETag, así que un ciclo sin cambios no descarga nada.
 */
'use strict';

const REFRESCO_MS = 30000;
const CLAVE_SEGUIDOS = 'ajp:seguidos';
const CLAVE_DIA = 'ajp:dia';
const CANAL_AJP = 'https://youtube.com/channel/UC7m2_Wx33tfrMYYVMVqIOzg/videos';
const MEDALLAS = { gold: '🥇', silver: '🥈', bronze: '🥉' };

let datos = null;
let etag = null;
let porId = new Map();      // id de combate -> combate
let vista = 'seguidos';
let dia = null;             // jornada seleccionada ('2026-09-26')

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

/* ---------- Jornadas ----------
   El torneo son dos días con los mismos horarios, así que hay que poder elegir
   cuál se mira; por defecto, el de hoy. */
function diasDelTorneo() {
  return [...new Set((datos?.matches || []).map((m) => m.day).filter(Boolean))].sort();
}

function etiquetaDia(iso) {
  const d = new Date(`${iso}T12:00:00`);
  return isNaN(d) ? iso
    : d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' });
}

function diaPorDefecto() {
  const dias = diasDelTorneo();
  if (!dias.length) return null;
  let guardado = null;
  try { guardado = localStorage.getItem(CLAVE_DIA); } catch { /* sin persistencia */ }
  if (guardado && dias.includes(guardado)) return guardado;
  const hoy = new Date().toISOString().slice(0, 10);
  return dias.includes(hoy) ? hoy : dias[0];
}

function pintarDias() {
  const caja = $('#dias');
  const dias = diasDelTorneo();
  // Con una sola jornada el selector sobra y solo quita sitio.
  caja.innerHTML = dias.length > 1
    ? dias.map((d) => `<button class="dia ${d === dia ? 'activo' : ''}" data-dia="${d}">
        ${escapar(etiquetaDia(d))}</button>`).join('')
    : '';
}

// Los combates de la jornada elegida. Las fichas de atleta enseñan todos, para
// no esconder que alguien compite también el otro día.
function deLaJornada(combates) {
  return dia ? combates.filter((c) => c.day === dia) : combates;
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
    if (!dia || !diasDelTorneo().includes(dia)) dia = diaPorDefecto();
    pintarDias();

    const eventos = datos.events || [];
    if (eventos.length) {
      const etiquetas = eventos.map((e) => e.label || e.id).join(' + ');
      $('#nombre-evento').textContent = eventos.length === 1
        ? (eventos[0].name || etiquetas)
        : `AJP Madrid · ${etiquetas}`;
      document.title = $('#nombre-evento').textContent;
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

// Se compara por athleteId, no por inscripción: la misma persona tiene un
// event_registration_id distinto en cada uno de los dos eventos.
function rivalDe(combate, athleteId) {
  return combate.sides.find((s) => s.athleteId !== athleteId) || null;
}

function etiquetaEvento(combate) {
  return combate.eventLabel
    ? `<span class="etiqueta evento">${escapar(combate.eventLabel)}</span>` : '';
}

function etiquetaResultado(combate, athleteId) {
  if (combate.state === 'running') return '<span class="etiqueta vivo">EN CURSO</span>';
  if (combate.state !== 'finished') return '<span class="etiqueta">Pendiente</span>';

  const yo = combate.sides.find((s) => s.athleteId === athleteId);
  if (!yo) return '<span class="etiqueta">Terminado</span>';
  const clase = yo.isWinner ? 'ganado' : 'perdido';
  const texto = yo.isWinner ? 'Ganó' : 'Perdió';
  const modo = combate.wonBy ? ` · ${combate.wonBy}` : '';
  return `<span class="etiqueta ${clase}">${texto}${escapar(modo)}</span>`;
}

function filaCombate(combate, athleteId) {
  const rival = rivalDe(combate, athleteId);
  const nombreRival = rival ? rival.name : 'Por determinar';
  const ronda = combate.round ? `${escapar(combate.round)} · ` : '';
  const otroDia = combate.day && combate.day !== dia
    ? `<span class="etiqueta">${escapar(etiquetaDia(combate.day).split(',')[0])}</span> ` : '';
  return `
    <div class="combate">
      <span class="hora">${hora(combate.estimatedStart)}</span>
      <span class="detalle-combate">
        <span class="rival">vs ${escapar(nombreRival)}</span><br>
        <span class="sub">${otroDia}${etiquetaEvento(combate)} ${ronda}${escapar(combate.mat || '')}</span>
      </span>
      ${etiquetaResultado(combate, athleteId)}
    </div>`;
}

/* ---------- Vistas ---------- */
function tarjetaAtleta(atleta, { conCombates = false } = {}) {
  const sigue = seguidos.has(atleta.id);
  const medalla = atleta.bestMedal
    ? `<span class="medalla" data-m="${atleta.bestMedal}">${MEDALLAS[atleta.bestMedal]}</span>` : '';
  const foto = atleta.image
    ? `<img class="foto" src="${escapar(atleta.image)}" alt="" loading="lazy">`
    : '<span class="foto"></span>';

  let combates = '';
  if (conCombates) {
    const lista = combatesDe(atleta);
    combates = lista.length
      ? lista.map((c) => filaCombate(c, atleta.id)).join('')
      : '<p class="sub">Sin combates en el schedule todavía.</p>';
  }

  return `
    <article class="tarjeta">
      <div class="tarjeta-cabecera">
        ${foto}
        <span class="crece" data-atleta="${escapar(atleta.id)}">
          <span class="nombre">${escapar(atleta.name)} ${medalla}</span><br>
          <span class="sub">${escapar(atleta.club || '—')} · ${escapar(atleta.categories[0] || '')}</span>
        </span>
        <button class="seguir ${sigue ? 'activo' : ''}"
                data-seguir="${escapar(atleta.id)}">${sigue ? 'Siguiendo' : 'Seguir'}</button>
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

  const mios = datos.athletes.filter((a) => seguidos.has(a.id));
  if (!mios.length) {
    caja.innerHTML = `<p class="vacio">Tus atletas no aparecen en estos eventos.</p>`;
    return;
  }

  // Lo primero que quiere ver alguien en el pabellón: qué toca ahora y qué viene.
  const proximos = [];
  for (const a of mios) {
    for (const c of deLaJornada(combatesDe(a))) {
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
            <span class="sub">vs ${escapar((rivalDe(combate, atleta.id) || {}).name || 'Por determinar')}
              · ${etiquetaEvento(combate)} ${escapar(combate.mat || '')}</span>
          </span>
          ${etiquetaResultado(combate, atleta.id)}
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
  // Se agrupa por NOMBRE de tatami, no por evento: en el pabellón hay seis
  // tatamis físicos y los cuatro bloques (Gi/No-Gi × sábado/domingo) los
  // reutilizan con ids distintos. Quien está delante del Mat 3 quiere ver qué
  // toca ahí, sea del evento que sea.
  const porMat = new Map();
  for (const m of datos.mats) {
    if (!porMat.has(m.name)) porMat.set(m.name, []);
  }
  for (const c of deLaJornada(datos.matches)) {
    if (porMat.has(c.mat)) porMat.get(c.mat).push(c);
  }

  const streams = new Map((datos.streams || []).map((s) => [s.mat, s.url]));

  const tarjeta = (nombre) => {
    const combates = (porMat.get(nombre) || [])
      .sort((a, b) => (a.estimatedStart || '').localeCompare(b.estimatedStart || ''));
    const enCurso = combates.filter((c) => c.state === 'running');
    const siguientes = combates.filter((c) => c.state !== 'finished' && c.state !== 'running');
    const mostrar = [...enCurso, ...siguientes].slice(0, 5);
    const url = streams.get(nombre);

    return `
      <article class="tarjeta">
        <div class="tarjeta-cabecera">
          <span class="crece">
            <span class="nombre">${escapar(nombre)}</span><br>
            <span class="sub">${combates.length} combates · ${enCurso.length} en curso</span>
          </span>
        </div>
        ${mostrar.length
          ? mostrar.map((c) => `
            <div class="combate">
              <span class="hora">${hora(c.estimatedStart)}</span>
              <span class="detalle-combate">
                <span class="rival">${escapar(c.sides.map((s) => s.name).join(' vs ') || 'Por determinar')}</span><br>
                <span class="sub">${etiquetaEvento(c)} ${escapar(c.category.raw || '')}</span>
              </span>
              ${c.state === 'running' ? '<span class="etiqueta vivo">EN CURSO</span>' : ''}
            </div>`).join('')
          : '<p class="sub">Sin combates pendientes.</p>'}
        ${url ? `<a class="enlace-stream" href="${escapar(url)}" target="_blank" rel="noopener">Ver retransmisión ↗</a>` : ''}
      </article>`;
  };

  const nombres = [...porMat.keys()].sort();
  caja.innerHTML = (nombres.length
    ? nombres.map(tarjeta).join('')
    : '<p class="vacio">Todavía no hay tatamis publicados.</p>')
    + `<p class="sub" style="text-align:center;margin-top:1rem">
         <a class="enlace-stream" href="${CANAL_AJP}" target="_blank" rel="noopener">
           Canal de YouTube de AJP ↗</a></p>`;
}

function pintar() {
  if (!datos) return;
  pintarEstado();
  if (vista === 'seguidos') pintarSeguidos();
  else if (vista === 'buscar') pintarBusqueda();
  else pintarTatamis();
}

/* ---------- Detalle de atleta ---------- */
function abrirDetalle(athleteId) {
  const atleta = datos.athletes.find((a) => a.id === athleteId);
  if (!atleta) return;

  $('#detalle-nombre').textContent = atleta.name;
  const medallas = atleta.medals.length
    ? `<p class="sub">${atleta.medals.map((m) =>
        `${MEDALLAS[m.medal]} ${escapar(m.category || '')}`).join('<br>')}</p>`
    : '';
  // Si compite en los dos eventos conviene que se vea: sus combates de Gi y
  // No-Gi aparecen mezclados en una sola lista ordenada por hora.
  const enEventos = (atleta.events || [])
    .map((id) => (datos.events.find((e) => e.id === id) || {}).label || id);
  const eventos = enEventos.length > 1
    ? `<p class="sub">Compite en: ${escapar(enEventos.join(' y '))}</p>` : '';
  $('#detalle-cuerpo').innerHTML = `
    <p class="sub">${escapar(atleta.club || '—')}${atleta.country ? ' · ' + escapar(atleta.country) : ''}</p>
    ${eventos}
    ${medallas}
    <h3 class="seccion-titulo">Combates</h3>
    ${combatesDe(atleta).map((c) => filaCombate(c, atleta.id)).join('') || '<p class="sub">Sin combates.</p>'}`;
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
  const botonDia = ev.target.closest('[data-dia]');
  if (botonDia) {
    dia = botonDia.dataset.dia;
    try { localStorage.setItem(CLAVE_DIA, dia); } catch { /* sin persistencia */ }
    pintarDias();
    pintar();
    return;
  }
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
