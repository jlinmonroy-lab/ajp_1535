/* Utilidades compartidas por la pantalla de inicio (buscador.js) y la de evento
 * (app.js). Sin dependencias ni build: scripts clásicos que comparten el ámbito
 * global, así que el orden de carga en index.html importa. */
'use strict';

const $ = (sel) => document.querySelector(sel);

// Buscar "muñoz" debe encontrar "Muñoz", y "jose" debe encontrar "José".
const normalizar = (texto) => (texto || '')
  .toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

function escapar(texto) {
  const d = document.createElement('div');
  d.textContent = texto == null ? '' : String(texto);
  return d.innerHTML;
}

/* ---------- Almacenamiento local ----------
   Puede fallar (modo privado, cookies bloqueadas) y la app debe seguir
   funcionando sin ello, así que todo acceso va envuelto. */
function leerLocal(clave, porDefecto) {
  try {
    const valor = JSON.parse(localStorage.getItem(clave));
    return valor == null ? porDefecto : valor;
  } catch {
    return porDefecto;
  }
}

function guardarLocal(clave, valor) {
  try {
    localStorage.setItem(clave, JSON.stringify(valor));
  } catch { /* sin persistencia, pero la sesión sigue */ }
}

/* ---------- Fechas ---------- */
// 'YYYY-MM-DD' -> Date a mediodía, para que ninguna zona horaria la cambie de día.
function fechaLocal(iso) {
  const d = new Date(`${iso}T12:00:00`);
  return isNaN(d) ? null : d;
}

// '17 oct 2026', o '17–18 oct 2026' si dura más de un día.
function rangoFechas(inicio, fin) {
  const a = fechaLocal(inicio);
  if (!a) return '';
  const completa = (d) => d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
  const b = fin && fin !== inicio ? fechaLocal(fin) : null;
  if (!b) return completa(a);
  if (a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()) {
    return `${a.getDate()}–${completa(b)}`;
  }
  return `${completa(a)} – ${completa(b)}`;
}

/* ---------- Red ---------- */
// Las respuestas de error de la API traen {error: "..."}; esto lo saca si está.
async function mensajeDeError(resp) {
  try {
    const cuerpo = await resp.json();
    if (cuerpo && cuerpo.error) return cuerpo.error;
  } catch { /* no era JSON */ }
  return `HTTP ${resp.status}`;
}
