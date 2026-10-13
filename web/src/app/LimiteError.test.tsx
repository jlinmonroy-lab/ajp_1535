import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LimiteError } from './LimiteError';

function Bomba({ fallar = true }: { fallar?: boolean }) {
  if (fallar) throw new Error('boom');
  return <p>todo bien</p>;
}

// React cuenta por consola lo que atrapa un límite; aquí se silencia para ver solo lo que importa.
const consola = vi.spyOn(console, 'error').mockImplementation(() => {});
afterEach(() => consola.mockClear());

describe('LimiteError', () => {
  it('con hijos que funcionan, no pinta nada suyo', () => {
    render(<LimiteError mensaje="Algo falló"><Bomba fallar={false} /></LimiteError>);
    expect(screen.getByText('todo bien')).toBeInTheDocument();
    expect(screen.queryByText('Algo falló')).toBeNull();
  });

  it('si un hijo falla al pintarse, dice que falló en vez de dejar la pantalla en blanco', () => {
    render(<LimiteError mensaje="Algo falló"><Bomba /></LimiteError>, { onCaughtError: () => {} });
    expect(screen.getByText('Algo falló')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Recargar' })).toBeNull();
  });

  it('la raíz de la web ofrece recargar', () => {
    render(<LimiteError mensaje="Algo falló" recargable><Bomba /></LimiteError>, { onCaughtError: () => {} });
    expect(screen.getByText(/Algo falló/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recargar' })).toBeInTheDocument();
  });

  it('React avisa a la raíz de lo que atrapa, con la pila de componentes', () => {
    const alCaer = vi.fn();
    render(<LimiteError mensaje="Algo falló"><Bomba /></LimiteError>, { onCaughtError: alCaer });
    expect(alCaer).toHaveBeenCalledTimes(1);
    const [error, info] = alCaer.mock.calls[0]!;
    expect(error).toMatchObject({ message: 'boom' });
    expect(info.componentStack).toContain('Bomba');
  });

  it('se recupera solo cuando cambia `reinicio`', () => {
    const { rerender } = render(
      <LimiteError mensaje="Algo falló" reinicio="a"><Bomba /></LimiteError>, { onCaughtError: () => {} });
    expect(screen.getByText('Algo falló')).toBeInTheDocument();

    rerender(<LimiteError mensaje="Algo falló" reinicio="a"><Bomba fallar={false} /></LimiteError>);
    expect(screen.getByText('Algo falló')).toBeInTheDocument();      // sigue igual: no se reintenta

    rerender(<LimiteError mensaje="Algo falló" reinicio="b"><Bomba fallar={false} /></LimiteError>);
    expect(screen.getByText('todo bien')).toBeInTheDocument();
  });
});
