import { describe, expect, it } from 'vitest';
import type { Atleta, Combate, Datos } from '../tipos';
import {
  filaDeAtleta, filaDeTatami, hace, llavesDe, resultadoDe, rivalDe, sinSchedule, textoEstado, urlDelEvento,
} from './selectores';

function combate(extra: Partial<Combate> = {}): Combate {
  return {
    id: '1-1', eventId: '1', eventLabel: null, bracketId: '1-9', bracketUrl: null, mat: 'Mat 3',
    round: 'Semifinal', category: { raw: "Men's GI / Black / 77KG" },
    estimatedStart: '2026-10-17T10:30:00', day: '2026-10-17', state: 'finished', wonBy: null,
    sides: [
      { athleteId: 'ana|club', registrationId: '1', name: 'Ana', club: null, country: null, image: null, isWinner: true },
      { athleteId: 'eva|club', registrationId: '2', name: 'Eva', club: null, country: null, image: null, isWinner: false },
    ],
    ...extra,
  };
}

function datos(extra: Partial<Datos> = {}): Datos {
  return {
    events: [{ id: '1', label: null, name: 'Open', published: true }],
    fetchedAt: new Date('2026-10-17T10:00:00Z').toISOString(),
    stale: false, staleSince: null, mats: [], matches: [combate()], athletes: [],
    ...extra,
  };
}

describe('resultadoDe', () => {
  it('en curso y pendiente', () => {
    expect(resultadoDe(combate({ state: 'running' }), 'ana|club')).toEqual({ texto: 'EN CURSO', tono: 'vivo' });
    expect(resultadoDe(combate({ state: 'seeded' }), 'ana|club')).toEqual({ texto: 'Pendiente' });
  });

  it('ganó y perdió, con la forma de ganar si se sabe', () => {
    expect(resultadoDe(combate({ wonBy: 'puntos' }), 'ana|club')).toEqual({ texto: 'Ganó · puntos', tono: 'ganado' });
    expect(resultadoDe(combate(), 'eva|club')).toEqual({ texto: 'Perdió', tono: 'perdido' });
  });

  it('un terminado en el que no está el atleta', () => {
    expect(resultadoDe(combate(), 'otra|club')).toEqual({ texto: 'Terminado' });
  });
});

describe('rivalDe', () => {
  it('compara por athleteId y no por inscripción', () => {
    expect(rivalDe(combate(), 'ana|club')?.name).toBe('Eva');
    expect(rivalDe(combate({ sides: [] }), 'ana|club')).toBeNull();
  });
});

describe('filas de combate', () => {
  it('vista de atleta: contra quién, ronda y tatami', () => {
    const fila = filaDeAtleta(combate({ eventLabel: 'Gi' }), 'ana|club');
    expect(fila).toMatchObject({
      titulo: 'vs Eva', evento: 'Gi', detalle: 'Semifinal · Mat 3',
      resultado: { texto: 'Ganó', tono: 'ganado' },
    });
    expect(fila.dia).toBeTruthy();
  });

  it('sin rival conocido dice «Por determinar»', () => {
    expect(filaDeAtleta(combate({ sides: [combate().sides[0]!] }), 'ana|club').titulo).toBe('vs Por determinar');
  });

  it('vista de tatami: quiénes pelean y solo marca el que está en curso', () => {
    expect(filaDeTatami(combate({ state: 'running' }))).toMatchObject({
      titulo: 'Ana vs Eva', detalle: "Men's GI / Black / 77KG", resultado: { texto: 'EN CURSO' },
    });
    expect(filaDeTatami(combate({ state: 'seeded' })).resultado).toBeUndefined();
  });
});

describe('llavesDe', () => {
  const atleta = (cuadros: Atleta['brackets']) => ({ brackets: cuadros }) as Atleta;
  const cuadro = (n: number, extra = {}) => ({ id: `b${n}`, category: `Cat ${n}`, eventLabel: null, url: `https://x.test/${n}`, ...extra });

  it('con un solo cuadro, «Ver llave»', () => {
    expect(llavesDe(atleta([cuadro(1)]))).toEqual([{ url: 'https://x.test/1', texto: 'Ver llave' }]);
  });

  it('con varios cuadros se distinguen por categoría (y evento)', () => {
    expect(llavesDe(atleta([cuadro(1, { eventLabel: 'Gi' }), cuadro(2)])).map((l) => l.texto))
      .toEqual(['Gi · Cat 1', 'Cat 2']);
  });

  it('conCategoria fuerza la categoría aunque haya uno solo', () => {
    expect(llavesDe(atleta([cuadro(1)]), { conCategoria: true })[0]?.texto).toBe('Cat 1');
  });
});

describe('evento', () => {
  it('urlDelEvento solo con un evento; usa baseUrl si no hay url', () => {
    expect(urlDelEvento(datos({ events: [{ id: '5', label: null, name: 'A', url: 'https://a.test/e' }] }))).toBe('https://a.test/e');
    expect(urlDelEvento(datos({ events: [{ id: '5', label: null, name: 'A', baseUrl: 'https://b.test' }] }))).toBe('https://b.test/es/event/5');
    expect(urlDelEvento(datos({ events: [
      { id: '1', label: null, name: 'A' }, { id: '2', label: null, name: 'B' }] }))).toBeUndefined();
    expect(urlDelEvento(null)).toBeUndefined();
  });

  it('sinSchedule solo si todos los eventos están sin publicar', () => {
    const e = (published?: boolean) => ({ id: '1', label: null, name: 'A', published });
    expect(sinSchedule(datos({ events: [e(false), e(false)] }))).toBe(true);
    expect(sinSchedule(datos({ events: [e(false), e(true)] }))).toBe(false);
    expect(sinSchedule(datos({ events: [e(undefined)] }))).toBe(false);
    expect(sinSchedule(null)).toBe(false);
  });
});

describe('hace', () => {
  const t0 = new Date('2026-10-17T10:00:00Z').getTime();
  it('segundos, minutos y horas', () => {
    expect(hace(new Date(t0).toISOString(), t0 + 12_000)).toBe('hace 12s');
    expect(hace(new Date(t0).toISOString(), t0 + 5 * 60_000)).toBe('hace 5 min');
    expect(hace(new Date(t0).toISOString(), t0 + 3 * 3_600_000)).toBe('hace 3 h');
  });

  it('un reloj adelantado no da tiempos negativos', () => {
    expect(hace(new Date(t0 + 60_000).toISOString(), t0)).toBe('hace 0s');
  });
});

describe('textoEstado', () => {
  const base = { esPanel: false, modoEstatico: false };
  const tFetch = new Date('2026-10-17T10:00:00Z').getTime();
  const d = datos({ fetchedAt: new Date(tFetch).toISOString() });

  it('antes de datos y según la situación del ciclo', () => {
    expect(textoEstado({ ...base, datos: null, situacion: { tipo: 'cargando' }, ahora: tFetch }))
      .toEqual({ texto: 'Cargando…', vieja: false });
    expect(textoEstado({ ...base, datos: null, situacion: { tipo: 'leyendo', titulo: null }, ahora: tFetch }).texto)
      .toMatch(/^Leyendo el schedule/);
    expect(textoEstado({ ...base, datos: null, situacion: { tipo: 'inexistente', mensaje: 'x' }, ahora: tFetch }))
      .toEqual({ texto: 'Ese evento no existe', vieja: true });
    expect(textoEstado({ ...base, datos: null, situacion: { tipo: 'error', mensaje: 'Sin conexión (x)' }, ahora: tFetch }))
      .toEqual({ texto: 'Sin conexión (x)', vieja: true });
  });

  it('un error con datos en pantalla dice qué edad tienen: sin ella parecerían frescos', () => {
    const error = { tipo: 'error', mensaje: 'Sin conexión (x)' } as const;
    expect(textoEstado({ ...base, datos: d, situacion: error, ahora: tFetch + 90_000 }))
      .toEqual({ texto: 'Sin conexión (x) · últimos datos hace 1 min', vieja: true });
  });

  it('datos frescos: cuánto hace y el total', () => {
    expect(textoEstado({ ...base, datos: d, situacion: { tipo: 'ok' }, ahora: tFetch + 12_000 }))
      .toEqual({ texto: 'Actualizado hace 12s · 1 combates · 0 atletas', vieja: false });
  });

  it('stale (lo marca el servidor) avisa con la hora desde la que no se actualiza', () => {
    const r = textoEstado({
      ...base, situacion: { tipo: 'ok' }, ahora: tFetch,
      datos: datos({ stale: true, staleSince: new Date(tFetch).toISOString() }),
    });
    expect(r.vieja).toBe(true);
    expect(r.texto).toMatch(/^⚠ Datos sin actualizar desde \d{2}:\d{2} · 1 combates/);
  });

  it('más de 4 min sin datos nuevos avisa, y en el panel estático sugiere mirar el scraper', () => {
    const tarde = tFetch + 5 * 60_000;
    const normal = textoEstado({ ...base, datos: d, situacion: { tipo: 'ok' }, ahora: tarde });
    expect(normal).toEqual({ texto: '⚠ Sin actualizarse desde hace 5 min · 1 combates · 0 atletas', vieja: true });
    const panel = textoEstado({ esPanel: true, modoEstatico: true, datos: d, situacion: { tipo: 'ok' }, ahora: tarde });
    expect(panel.texto).toContain('¿está corriendo el scraper?');
  });

  it('sin schedule publicado lo dice y no alarma', () => {
    const sin = datos({ events: [{ id: '1', label: null, name: 'A', published: false }] });
    expect(textoEstado({ ...base, datos: sin, situacion: { tipo: 'ok' }, ahora: tFetch + 10 * 60_000 }))
      .toEqual({ texto: 'Schedule sin publicar · se vuelve a comprobar solo', vieja: false });
  });
});
