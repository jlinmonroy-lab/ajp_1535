import { describe, expect, it } from 'vitest';
import { ErrorDatos, esDatos, problemaConDatos } from './validar';

const bueno = () => ({
  events: [{ id: '1', label: null, name: 'Open' }],
  fetchedAt: '2026-10-17T10:00:00Z',
  stale: false, staleSince: null, mats: [], matches: [], athletes: [],
});

describe('problemaConDatos', () => {
  it('unos datos completos no tienen problema', () => {
    expect(problemaConDatos(bueno())).toBeNull();
    expect(esDatos(bueno())).toBe(true);
  });

  it('es laxo: campos de más o opcionales ausentes no tumban unos datos que se pueden pintar', () => {
    const { stale: _stale, staleSince: _desde, ...sinOpcionales } = bueno();
    expect(problemaConDatos({ ...sinOpcionales, campoNuevo: { de: 'un futuro' }, streams: [] })).toBeNull();
  });

  it.each([null, undefined, 'texto', 42, [], true])('rechaza %j: no es un objeto', (valor) => {
    expect(problemaConDatos(valor)).toBe('no es un objeto');
    expect(esDatos(valor)).toBe(false);
  });

  it.each(['events', 'matches', 'athletes', 'mats'])('rechaza si falta la lista «%s» o no es una lista', (campo) => {
    const sin: Record<string, unknown> = bueno();
    delete sin[campo];
    expect(problemaConDatos(sin)).toBe(`falta la lista «${campo}»`);
    expect(problemaConDatos({ ...bueno(), [campo]: { 0: 'a' } })).toBe(`falta la lista «${campo}»`);
    expect(problemaConDatos({ ...bueno(), [campo]: null })).toBe(`falta la lista «${campo}»`);
  });

  it.each([undefined, null, 1760000000, '', 'ayer', '2026-13-45'])('rechaza un «fetchedAt» que no es una fecha: %j', (valor) => {
    expect(problemaConDatos({ ...bueno(), fetchedAt: valor })).toBe('«fetchedAt» no es una fecha');
  });

  it('el problema nombra el campo, nunca el valor', () => {
    const texto = problemaConDatos({ ...bueno(), events: 'Ana Pérez, Club Secreto' });
    expect(texto).not.toContain('Ana');
    expect(texto).not.toContain('Secreto');
  });
});

describe('ErrorDatos', () => {
  it('es un Error con nombre propio, para distinguirlo de un fallo de red o del servidor', () => {
    const e = new ErrorDatos('x');
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe('ErrorDatos');
    expect(e.message).toBe('x');
  });
});
