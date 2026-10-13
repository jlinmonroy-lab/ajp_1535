/* El contrato con Python: lo que declara `tipos.ts` frente a lo que emite `construir_estado`.
 *
 * Los dos lados no se ven. Esta prueba lee la muestra que genera tests/contrato.py (el código
 * de verdad de scraper/parse.py sobre fixtures anonimizadas) y comprueba que cada campo que la
 * web declara está ahí, con el tipo declarado. Es de un solo sentido a propósito: `tipos.ts` es
 * parcial (solo declara lo que la web usa), así que a Python le sobran campos y no pasa nada.
 *
 * Qué rompe qué:
 *   - Python renombra o quita un campo, o pone un null donde la web espera texto: falla esta prueba.
 *   - Alguien añade o cambia un campo en `tipos.ts`: falla `npm run typecheck` hasta que se
 *     describa aquí (los mapas son exhaustivos), y luego esta prueba dice si Python lo emite.
 *   - Python cambia lo que emite pero no regenera la muestra: falla tests/test_contrato.py.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type {
  Atleta, CategoriaCombate, Combate, Cuadro, Datos, EntradaGrupo, EventoDatos, LadoCombate,
  MedallaGanada, Retransmision, Tatami,
} from '../tipos';
import { MEDALLA } from './selectores';
import { esDatos } from './validar';

type Etiqueta = 'cadena' | 'cadena|nulo' | 'booleano' | 'lista' | 'objeto';

/** La etiqueta que le toca a un campo según su tipo: no se escribe a mano, se deduce. */
type EtiquetaDe<V> =
  [V] extends [string] ? 'cadena'
    : [V] extends [string | null] ? 'cadena|nulo'
      : [V] extends [boolean] ? 'booleano'
        : [V] extends [readonly unknown[]] ? 'lista'
          : [V] extends [object] ? 'objeto'
            : never;

/** Un campo por cada campo de la interfaz (exhaustivo), marcando los opcionales. */
type Campos<T> = {
  readonly [K in keyof T]-?: {} extends Pick<T, K>
    ? readonly [EtiquetaDe<Exclude<T[K], undefined>>, 'opcional']
    : readonly [EtiquetaDe<T[K]>];
};

const DATOS: Campos<Datos> = {
  events: ['lista'], group: ['objeto', 'opcional'], fetchedAt: ['cadena'], stale: ['booleano'],
  staleSince: ['cadena|nulo'], mats: ['lista'], streams: ['lista', 'opcional'],
  matches: ['lista'], athletes: ['lista'],
};
const EVENTO: Campos<EventoDatos> = {
  id: ['cadena'], label: ['cadena|nulo'], name: ['cadena|nulo'], url: ['cadena', 'opcional'],
  baseUrl: ['cadena', 'opcional'], startdate: ['cadena', 'opcional'], enddate: ['cadena', 'opcional'],
  city: ['cadena', 'opcional'], country: ['cadena', 'opcional'], published: ['booleano', 'opcional'],
};
const TATAMI: Campos<Tatami> = { key: ['cadena'], name: ['cadena|nulo'] };
const RETRANSMISION: Campos<Retransmision> = { mat: ['cadena'], url: ['cadena'] };
const ENTRADA_GRUPO: Campos<EntradaGrupo> = { id: ['cadena'], name: ['cadena'], club: ['cadena|nulo', 'opcional'] };
const CATEGORIA: Campos<CategoriaCombate> = { raw: ['cadena|nulo'] };
const LADO: Campos<LadoCombate> = {
  athleteId: ['cadena'], registrationId: ['cadena'], name: ['cadena|nulo'], club: ['cadena|nulo'],
  country: ['cadena|nulo'], image: ['cadena|nulo'], isWinner: ['booleano'],
};
const COMBATE: Campos<Combate> = {
  id: ['cadena'], eventId: ['cadena'], eventLabel: ['cadena|nulo'], bracketId: ['cadena|nulo'],
  bracketUrl: ['cadena|nulo'], mat: ['cadena|nulo'], round: ['cadena|nulo'], category: ['objeto'],
  estimatedStart: ['cadena|nulo'], day: ['cadena|nulo'], state: ['cadena|nulo'], wonBy: ['cadena|nulo'],
  sides: ['lista'],
};
const MEDALLA_GANADA: Campos<MedallaGanada> = {
  bracketId: ['cadena'], eventId: ['cadena'], category: ['cadena|nulo'], medal: ['cadena'],
};
const CUADRO: Campos<Cuadro> = { id: ['cadena'], category: ['cadena|nulo'], eventLabel: ['cadena|nulo'], url: ['cadena'] };
const ATLETA: Campos<Atleta> = {
  id: ['cadena'], events: ['lista'], name: ['cadena'], club: ['cadena|nulo'], country: ['cadena|nulo'],
  image: ['cadena|nulo'], categories: ['lista'], brackets: ['lista'], matchIds: ['lista'],
  medals: ['lista'], bestMedal: ['cadena|nulo'], inGroup: ['booleano', 'opcional'],
};

type Mapa = Readonly<Record<string, readonly [Etiqueta, 'opcional'?]>>;
type Objeto = Record<string, unknown>;

const MEDALLAS = Object.keys(MEDALLA);

function describir(valor: unknown): string {
  if (valor === null) return 'null';
  if (Array.isArray(valor)) return 'una lista';
  return typeof valor === 'object' ? 'un objeto' : `${typeof valor} (${JSON.stringify(valor)})`;
}

function cumple(etiqueta: Etiqueta, valor: unknown): boolean {
  switch (etiqueta) {
    case 'cadena': return typeof valor === 'string';
    case 'cadena|nulo': return typeof valor === 'string' || valor === null;
    case 'booleano': return typeof valor === 'boolean';
    case 'lista': return Array.isArray(valor);
    case 'objeto': return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
  }
}

/** Los campos que faltan o tienen otro tipo, con su ruta. Vacío si cumple. */
function comprobar(ruta: string, valor: unknown, campos: Mapa): string[] {
  if (typeof valor !== 'object' || valor === null || Array.isArray(valor)) {
    return [`${ruta}: no es un objeto, es ${describir(valor)}`];
  }
  const o = valor as Objeto;
  const problemas: string[] = [];
  for (const [campo, [etiqueta, opcional]] of Object.entries(campos)) {
    if (!(campo in o)) {
      if (!opcional) problemas.push(`${ruta}.${campo}: falta (la web lo declara como ${etiqueta})`);
    } else if (!cumple(etiqueta, o[campo])) {
      problemas.push(`${ruta}.${campo}: la web espera ${etiqueta} y llega ${describir(o[campo])}`);
    }
  }
  return problemas;
}

const lista = (valor: unknown): unknown[] => (Array.isArray(valor) ? valor : []);
const recorrer = (ruta: string, valores: unknown, campos: Mapa): string[] =>
  lista(valores).flatMap((v, i) => comprobar(`${ruta}[${i}]`, v, campos));

/** Todo lo que el contrato exige de unos datos: formas, valores permitidos y referencias entre listas. */
export function problemasDelContrato(datos: unknown): string[] {
  const problemas = comprobar('datos', datos, DATOS);
  if (problemas.length) return problemas;      // sin lo básico no se puede seguir
  const d = datos as Objeto;

  problemas.push(
    ...recorrer('events', d.events, EVENTO),
    ...recorrer('mats', d.mats, TATAMI),
    ...recorrer('streams', d.streams, RETRANSMISION),
    ...recorrer('matches', d.matches, COMBATE),
    ...recorrer('athletes', d.athletes, ATLETA),
  );
  if ('group' in d) {
    problemas.push(...comprobar('group', d.group, { name: ['cadena|nulo', 'opcional'], athletes: ['lista', 'opcional'] }));
    problemas.push(...recorrer('group.athletes', (d.group as Objeto).athletes, ENTRADA_GRUPO));
  }
  lista(d.matches).forEach((c, i) => {
    const m = c as Objeto;
    problemas.push(...comprobar(`matches[${i}].category`, m.category, CATEGORIA));
    problemas.push(...recorrer(`matches[${i}].sides`, m.sides, LADO));
  });
  lista(d.athletes).forEach((a, i) => {
    const at = a as Objeto;
    problemas.push(...recorrer(`athletes[${i}].brackets`, at.brackets, CUADRO));
    problemas.push(...recorrer(`athletes[${i}].medals`, at.medals, MEDALLA_GANADA));
    for (const m of lista(at.medals)) {
      const medal = (m as Objeto).medal;
      if (!MEDALLAS.includes(medal as string)) problemas.push(`athletes[${i}].medals: «${String(medal)}» no es una medalla (${MEDALLAS.join(', ')})`);
    }
    if (at.bestMedal !== null && !MEDALLAS.includes(at.bestMedal as string)) {
      problemas.push(`athletes[${i}].bestMedal: «${String(at.bestMedal)}» no es una medalla`);
    }
  });

  // Lo que la web busca por id y da por encontrado.
  const ids = (xs: unknown, campo: string) => new Set(lista(xs).map((x) => String((x as Objeto)[campo])));
  const eventos = ids(d.events, 'id');
  const combates = ids(d.matches, 'id');
  const atletas = ids(d.athletes, 'id');
  lista(d.matches).forEach((c, i) => {
    const m = c as Objeto;
    if (!eventos.has(String(m.eventId))) problemas.push(`matches[${i}].eventId «${String(m.eventId)}» no está en events`);
    for (const lado of lista(m.sides)) {
      const id = String((lado as Objeto).athleteId);
      if (!atletas.has(id)) problemas.push(`matches[${i}].sides: el atleta «${id}» no está en athletes`);
    }
  });
  lista(d.athletes).forEach((a, i) => {
    const at = a as Objeto;
    for (const id of lista(at.matchIds)) {
      if (!combates.has(String(id))) problemas.push(`athletes[${i}].matchIds: el combate «${String(id)}» no está en matches`);
    }
    for (const id of lista(at.events)) {
      if (!eventos.has(String(id))) problemas.push(`athletes[${i}].events: el evento «${String(id)}» no está en events`);
    }
  });
  return problemas;
}

// Con jsdom `import.meta.url` no es una URL de fichero: se parte de la carpeta de esta prueba.
const leerMuestra = (): Objeto =>
  JSON.parse(readFileSync(resolve(import.meta.dirname, '../pruebas/estado.contrato.json'), 'utf-8')) as Objeto;

describe('contrato con Python: la muestra de construir_estado cumple tipos.ts', () => {
  it('no tiene ningún problema', () => {
    expect(problemasDelContrato(leerMuestra())).toEqual([]);
  });

  it('la web la da por buenos datos (esDatos)', () => {
    expect(esDatos(leerMuestra())).toBe(true);
  });

  it('la muestra tiene de qué fiarse: listas con contenido y las tres medallas', () => {
    const d = leerMuestra();
    for (const campo of ['events', 'mats', 'matches', 'athletes', 'streams']) {
      expect(lista(d[campo]).length, campo).toBeGreaterThan(0);
    }
    const medallas = new Set(lista(d.athletes).flatMap((a) => lista((a as Objeto).medals).map((m) => (m as Objeto).medal)));
    expect([...medallas].sort()).toEqual([...MEDALLAS].sort());
  });
});

describe('el propio contrato detecta lo que debe', () => {
  // Se parte de la muestra buena y se rompe una cosa cada vez.
  const rota = (romper: (d: Objeto) => void): string[] => {
    const d = leerMuestra();
    romper(d);
    return problemasDelContrato(d);
  };
  const primero = (d: Objeto, campo: string) => lista(d[campo])[0] as Objeto;

  it('un campo que Python deja de emitir', () => {
    expect(rota((d) => { delete primero(d, 'athletes')!.matchIds; }))
      .toEqual([expect.stringContaining('athletes[0].matchIds: falta')]);
  });

  it('un null donde la web espera texto: lo que revienta la pantalla', () => {
    expect(rota((d) => { primero(d, 'athletes')!.name = null; }))
      .toEqual(['athletes[0].name: la web espera cadena y llega null']);
    expect(rota((d) => { primero(d, 'mats')!.key = null; }))
      .toEqual(['mats[0].key: la web espera cadena y llega null']);
  });

  it('un campo anidado con otro tipo', () => {
    expect(rota((d) => { (lista(primero(d, 'matches')!.sides)[0] as Objeto).isWinner = 'sí'; }))
      .toEqual([expect.stringContaining('matches[0].sides[0].isWinner: la web espera booleano')]);
  });

  it('una medalla que la web no sabe pintar', () => {
    const problemas = rota((d) => {
      const conMedalla = lista(d.athletes).find((a) => lista((a as Objeto).medals).length) as Objeto;
      (lista(conMedalla.medals)[0] as Objeto).medal = 'platino';
    });
    expect(problemas).toEqual([expect.stringContaining('«platino» no es una medalla')]);
  });

  it('una referencia que no se encuentra', () => {
    expect(rota((d) => { (primero(d, 'athletes')!.matchIds as string[]).push('no-existe'); }))
      .toEqual([expect.stringContaining('el combate «no-existe» no está en matches')]);
    expect(rota((d) => { primero(d, 'matches')!.eventId = '999'; }))
      .toEqual([expect.stringContaining('eventId «999» no está en events')]);
  });

  it('un opcional ausente vale, pero presente con otro tipo no', () => {
    expect(rota((d) => { delete primero(d, 'athletes')!.inGroup; })).toEqual([]);
    expect(rota((d) => { primero(d, 'athletes')!.inGroup = null; }))
      .toEqual([expect.stringContaining('athletes[0].inGroup: la web espera booleano')]);
  });

  it('campos de más en Python no molestan: tipos.ts es parcial a propósito', () => {
    expect(rota((d) => { primero(d, 'mats')!.campoNuevo = { de: 'un futuro' }; })).toEqual([]);
  });

  it('un estado que ni es un objeto no explota', () => {
    expect(problemasDelContrato(null)).toEqual(['datos: no es un objeto, es null']);
    expect(problemasDelContrato({ events: 'x' }).length).toBeGreaterThan(0);
  });
});
