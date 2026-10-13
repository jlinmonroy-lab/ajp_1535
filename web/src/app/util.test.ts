import { describe, expect, it, vi } from 'vitest';
import { borrarLocal, guardarLocal, idDeEvento, leerLocal, normalizar, rangoFechas } from './util';

describe('normalizar', () => {
  it('ignora mayúsculas y tildes para que «jose» encuentre «José»', () => {
    expect(normalizar('José')).toBe('jose');
    expect(normalizar('MUÑOZ')).toBe('munoz');
  });

  it('tolera null y undefined', () => {
    expect(normalizar(null)).toBe('');
    expect(normalizar(undefined)).toBe('');
  });
});

describe('idDeEvento', () => {
  it('saca el número de un enlace de Smoothcomp, con o sin subdominio e idioma', () => {
    expect(idDeEvento('https://spainbjjtour.smoothcomp.com/es/event/33588')).toBe('33588');
    expect(idDeEvento('https://smoothcomp.com/en/event/1535?tab=schedule')).toBe('1535');
  });

  it('acepta un número, o hasta tres separados por comas', () => {
    expect(idDeEvento('33588')).toBe('33588');
    expect(idDeEvento(' 1535 , 1526 ')).toBe('1535,1526');
    expect(idDeEvento('007')).toBe('7');
  });

  it('rechaza lo que no es un evento', () => {
    expect(idDeEvento('madrid open')).toBeNull();
    expect(idDeEvento('1,2,3,4')).toBeNull();
    expect(idDeEvento('https://ejemplo.com/event/12')).toBeNull();
    expect(idDeEvento('')).toBeNull();
    expect(idDeEvento(null)).toBeNull();
  });
});

describe('rangoFechas', () => {
  const completa = (iso: string) => new Date(`${iso}T12:00:00`)
    .toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });

  it('un día suelto sale con su fecha completa', () => {
    expect(rangoFechas('2026-10-17')).toBe(completa('2026-10-17'));
    expect(rangoFechas('2026-10-17', '2026-10-17')).toBe(completa('2026-10-17'));
  });

  it('en el mismo mes no repite el mes: «17–18 oct 2026»', () => {
    expect(rangoFechas('2026-10-17', '2026-10-18')).toBe(`17–${completa('2026-10-18')}`);
  });

  it('en meses distintos pone las dos fechas completas', () => {
    expect(rangoFechas('2026-10-31', '2026-11-01'))
      .toBe(`${completa('2026-10-31')} – ${completa('2026-11-01')}`);
  });

  it('sin fecha válida, cadena vacía', () => {
    expect(rangoFechas(null)).toBe('');
    expect(rangoFechas('no-es-fecha')).toBe('');
  });
});

describe('almacenamiento local', () => {
  it('guarda y lee JSON', () => {
    guardarLocal('prueba', { a: 1 });
    expect(leerLocal('prueba', null)).toEqual({ a: 1 });
    borrarLocal('prueba');
    expect(leerLocal('prueba', 'nada')).toBe('nada');
  });

  it('devuelve el valor por defecto con JSON roto', () => {
    localStorage.setItem('roto', '{no es json');
    expect(leerLocal('roto', [])).toEqual([]);
  });

  it('sigue funcionando si el navegador no deja usar localStorage', () => {
    const roto = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloqueado'); });
    const rotoEscritura = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado'); });
    expect(leerLocal('x', 'por defecto')).toBe('por defecto');
    expect(() => guardarLocal('x', 1)).not.toThrow();
    roto.mockRestore();
    rotoEscritura.mockRestore();
  });
});
