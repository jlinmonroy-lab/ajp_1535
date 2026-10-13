import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { idsDeHash, usarRutaHash } from './usarRutaHash';

describe('idsDeHash', () => {
  it('reconoce #/evento/ID y varios ids', () => {
    expect(idsDeHash('#/evento/33588')).toBe('33588');
    expect(idsDeHash('#/evento/1535,1526')).toBe('1535,1526');
  });

  it('todo lo demás es el inicio', () => {
    for (const hash of ['', '#', '#/', '#/evento/', '#/evento/abc', '#/evento/12/extra', '#/otra']) {
      expect(idsDeHash(hash)).toBeNull();
    }
  });
});

describe('usarRutaHash', () => {
  it('sigue los cambios de la URL', () => {
    location.hash = '#/';
    const { result } = renderHook(() => usarRutaHash());
    expect(result.current).toBeNull();

    act(() => { location.hash = '#/evento/1535'; window.dispatchEvent(new HashChangeEvent('hashchange')); });
    expect(result.current).toBe('1535');

    act(() => { location.hash = '#/'; window.dispatchEvent(new HashChangeEvent('hashchange')); });
    expect(result.current).toBeNull();
  });
});
