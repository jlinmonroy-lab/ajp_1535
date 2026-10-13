/* Utilidades puras de la web (sin React ni red). */

// Buscar "muñoz" debe encontrar "Muñoz", y "jose" debe encontrar "José".
export const normalizar = (texto: string | null | undefined): string => (texto ?? '')
  .toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

/* ---------- Almacenamiento local ----------
   Puede fallar (modo privado, cookies bloqueadas) y la app debe seguir
   funcionando sin ello, así que todo acceso va envuelto. */
export function leerLocal<T>(clave: string, porDefecto: T): T {
  try {
    const valor = JSON.parse(localStorage.getItem(clave) ?? 'null');
    return valor == null ? porDefecto : (valor as T);
  } catch {
    return porDefecto;
  }
}

export function guardarLocal(clave: string, valor: unknown): void {
  try {
    localStorage.setItem(clave, JSON.stringify(valor));
  } catch { /* sin persistencia, pero la sesión sigue */ }
}

export function borrarLocal(clave: string): void {
  try {
    localStorage.removeItem(clave);
  } catch { /* sin persistencia: no había nada que borrar */ }
}

/* ---------- Fechas ---------- */
// 'YYYY-MM-DD' -> Date a mediodía, para que ninguna zona horaria la cambie de día.
export function fechaLocal(iso: string | null | undefined): Date | null {
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

// '17 oct 2026', o '17–18 oct 2026' si dura más de un día.
export function rangoFechas(inicio: string | null | undefined, fin?: string | null): string {
  const a = fechaLocal(inicio);
  if (!a) return '';
  const completa = (d: Date) => d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
  const b = fin && fin !== inicio ? fechaLocal(fin) : null;
  if (!b) return completa(a);
  if (a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()) {
    return `${a.getDate()}–${completa(b)}`;
  }
  return `${completa(a)} – ${completa(b)}`;
}

/** Hoy como YYYY-MM-DD en hora local. */
export const hoy = (): string => new Date().toLocaleDateString('sv-SE');

/* ---------- Eventos ---------- */
// Pegar https://spainbjjtour.smoothcomp.com/es/event/33588 o escribir 33588 ofrece
// abrir ese evento directamente: es la salida si la búsqueda no está disponible.
export function idDeEvento(texto: string | null | undefined): string | null {
  const t = (texto ?? '').trim();
  const enlace = t.match(/smoothcomp\.com\/[^\s?#]*?\/event\/(\d{1,9})/i);
  if (enlace) return String(Number(enlace[1]));
  if (/^\d{1,9}(\s*,\s*\d{1,9}){0,2}$/.test(t)) {
    return t.split(',').map((n) => String(Number(n))).join(',');
  }
  return null;
}
