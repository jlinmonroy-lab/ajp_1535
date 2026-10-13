/* Comprueba que lo que llega del servidor tiene la forma que la web da por supuesta.
 *
 * `await resp.json()` solo garantiza que es JSON: un objeto sin `matches` pasaría el cast a
 * `Datos` y rompería el render mucho más tarde, con un error que no dice de dónde viene.
 *
 * Es laxo a propósito: solo se exige lo que la web desreferencia sin protección. Un campo
 * nuevo del servidor, o uno opcional que falte, no debe tumbar unos datos que se pueden pintar.
 */
import type { Datos } from '../tipos';

/** Unos datos que no se pueden pintar. Es distinto de un fallo de red o del servidor. */
export class ErrorDatos extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = 'ErrorDatos';
  }
}

// Las listas sobre las que la web hace .map/.find/.length sin `?.` (Evento.tsx, selectores.ts).
const LISTAS = ['events', 'matches', 'athletes', 'mats'] as const;

/** La primera cosa que no cuadra, o null si los datos sirven. Solo nombra campos, nunca valores. */
export function problemaConDatos(x: unknown): string | null {
  if (typeof x !== 'object' || x === null || Array.isArray(x)) return 'no es un objeto';
  const d = x as Record<string, unknown>;
  for (const campo of LISTAS) {
    if (!Array.isArray(d[campo])) return `falta la lista «${campo}»`;
  }
  // Sin una fecha válida, el «hace X» saldría como «hace NaN h».
  if (typeof d.fetchedAt !== 'string' || Number.isNaN(new Date(d.fetchedAt).getTime())) {
    return '«fetchedAt» no es una fecha';
  }
  return null;
}

export function esDatos(x: unknown): x is Datos {
  return problemaConDatos(x) === null;
}
