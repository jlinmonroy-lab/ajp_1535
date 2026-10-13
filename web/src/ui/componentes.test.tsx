import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  AccesoAdmin, Boton, Cabecera, ChipZona, EnlaceExterno, Filtros, FormAltaGrupo, ListaGrupo, Llaves, Medalla,
  PanelDetalle, Pestanas, TarjetaAtleta, TarjetaEvento,
} from '.';
import { esUrlSegura } from './urlSegura';

describe('esUrlSegura', () => {
  it('solo admite https', () => {
    expect(esUrlSegura('https://smoothcomp.com/es/event/1')).toBe(true);
    expect(esUrlSegura('HTTPS://smoothcomp.com')).toBe(true);
    for (const mala of ['http://smoothcomp.com', 'javascript:alert(1)', 'data:text/html,x', '//smoothcomp.com', '', null, undefined]) {
      expect(esUrlSegura(mala)).toBe(false);
    }
  });
});

describe('Boton', () => {
  it('es type="button" salvo que se diga otra cosa (no envía formularios sin querer)', () => {
    const { rerender } = render(<Boton>Seguir</Boton>);
    expect(screen.getByRole('button', { name: 'Seguir' })).toHaveAttribute('type', 'button');
    rerender(<Boton type="submit">Entrar</Boton>);
    expect(screen.getByRole('button', { name: 'Entrar' })).toHaveAttribute('type', 'submit');
  });

  it('con href seguro es un enlace que abre en otra pestaña sin pasar el opener', () => {
    render(<Boton variante="icono" href="https://smoothcomp.com/e/1" aria-label="Ver">↗</Boton>);
    const enlace = screen.getByRole('link', { name: 'Ver' });
    expect(enlace).toHaveAttribute('href', 'https://smoothcomp.com/e/1');
    expect(enlace).toHaveAttribute('target', '_blank');
    expect(enlace).toHaveAttribute('rel', 'noopener');
  });

  it('con href que no es https no pinta nada', () => {
    const { container } = render(<Boton href="javascript:alert(1)">x</Boton>);
    expect(container).toBeEmptyDOMElement();
  });

  it('activo y variante se notan en las clases', () => {
    render(<Boton variante="discontinuo" activo>Todos</Boton>);
    expect(screen.getByRole('button')).toHaveClass('fc-boton--discontinuo', 'fc-boton--activo');
  });
});

describe('EnlaceExterno y Llaves', () => {
  it('EnlaceExterno descarta lo que no es https', () => {
    const { container } = render(<EnlaceExterno href="http://x.test">x</EnlaceExterno>);
    expect(container).toBeEmptyDOMElement();
  });

  it('Llaves pinta solo las seguras y nada si no queda ninguna (sin contenedor vacío)', () => {
    const { container, rerender } = render(
      <Llaves llaves={[{ url: 'https://x.test/1', texto: 'Ver llave' }, { url: 'http://x.test/2', texto: 'Mala' }]} />);
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByRole('link')).toHaveTextContent('⤢ Ver llave');

    rerender(<Llaves llaves={[{ url: 'http://x.test/2', texto: 'Mala' }]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<Llaves llaves={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('Pestanas, Filtros y ChipZona', () => {
  it('Pestanas marca la activa, avisa del cambio y pinta el contador solo si se da', () => {
    const onCambiar = vi.fn();
    render(<Pestanas
      activa="seguidos" onCambiar={onCambiar}
      pestanas={[{ id: 'seguidos', etiqueta: 'Mis atletas', contador: 3 }, { id: 'buscar', etiqueta: 'Buscar' }]} />);
    expect(screen.getByRole('tab', { name: /Mis atletas/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Buscar' })).toHaveAttribute('aria-selected', 'false');
    expect(document.getElementById('contador-seguidos')).toHaveTextContent('3');
    expect(document.getElementById('contador-buscar')).toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: 'Buscar' }));
    expect(onCambiar).toHaveBeenCalledWith('buscar');
  });

  it('Pestanas con contador 0 deja la burbuja vacía', () => {
    render(<Pestanas activa="a" onCambiar={() => {}} pestanas={[{ id: 'a', etiqueta: 'A', contador: 0 }]} />);
    expect(document.getElementById('contador-a')).toBeEmptyDOMElement();
  });

  it('Filtros marca la elegida con aria-pressed', () => {
    const onCambiar = vi.fn();
    render(<Filtros etiqueta="Cuándo" valor="past" onCambiar={onCambiar}
      opciones={[{ id: 'upcoming', etiqueta: 'Próximos' }, { id: 'past', etiqueta: 'Pasados' }]} />);
    expect(screen.getByRole('group', { name: 'Cuándo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pasados' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Próximos' }));
    expect(onCambiar).toHaveBeenCalledWith('upcoming');
  });

  it('ChipZona muestra la ✕ solo encendido', () => {
    const { rerender } = render(<ChipZona nombre="Madrid, España" activo onAlternar={() => {}} />);
    expect(screen.getByRole('button')).toHaveTextContent('📍 Madrid, España ✕');
    rerender(<ChipZona nombre="Madrid, España" activo={false} onAlternar={() => {}} />);
    expect(screen.getByRole('button')).toHaveTextContent(/^📍 Madrid, España$/);
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('Medalla y TarjetaEvento', () => {
  it('Medalla se anuncia por su nombre', () => {
    render(<Medalla tipo="plata" />);
    expect(screen.getByRole('img', { name: 'Plata' })).toHaveTextContent('🥈');
  });

  it('TarjetaEvento es un enlace a la dirección dada, con su pastilla', () => {
    render(<TarjetaEvento href="#/evento/7" titulo="Open" detalle="17 oct" etiqueta={{ texto: 'Hoy', tono: 'vivo' }} />);
    expect(screen.getByRole('link')).toHaveAttribute('href', '#/evento/7');
    expect(screen.getByText('Hoy')).toHaveClass('fc-etiqueta--vivo');
  });
});

describe('TarjetaAtleta', () => {
  const base = { id: 'ana|club', nombre: 'Ana', club: 'Club', categoria: 'Men GI', siguiendo: false, onSeguir: () => {} };

  it('el botón dice Seguir o Siguiendo y avisa al pulsarlo', () => {
    const onSeguir = vi.fn();
    const { rerender } = render(<TarjetaAtleta {...base} onSeguir={onSeguir} />);
    fireEvent.click(screen.getByRole('button', { name: 'Seguir' }));
    expect(onSeguir).toHaveBeenCalledOnce();
    rerender(<TarjetaAtleta {...base} siguiendo />);
    expect(screen.getByRole('button', { name: 'Siguiendo' })).toHaveClass('fc-boton--activo');
  });

  it('tocar el nombre abre la ficha', () => {
    const onAbrir = vi.fn();
    render(<TarjetaAtleta {...base} onAbrir={onAbrir} />);
    fireEvent.click(screen.getByText('Ana'));
    expect(onAbrir).toHaveBeenCalledOnce();
  });

  it('sin combates, solo con la lista vacía dice que no hay (sin la lista no pinta la sección)', () => {
    const { rerender } = render(<TarjetaAtleta {...base} />);
    expect(screen.queryByText('Sin combates en el schedule todavía.')).toBeNull();
    rerender(<TarjetaAtleta {...base} combates={[]} />);
    expect(screen.getByText('Sin combates en el schedule todavía.')).toBeInTheDocument();
  });

  it('«Seguir para todos» cambia de texto según el estado y se bloquea guardando', () => {
    const onAlternar = vi.fn();
    const { rerender } = render(<TarjetaAtleta {...base} paraTodos={{ activo: false, onAlternar }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Seguir para todos' }));
    expect(onAlternar).toHaveBeenCalledOnce();
    rerender(<TarjetaAtleta {...base} paraTodos={{ activo: true, onAlternar }} />);
    expect(screen.getByRole('button', { name: '✓ Lo ve todo el grupo' })).toBeInTheDocument();
    rerender(<TarjetaAtleta {...base} paraTodos={{ activo: false, guardando: true, onAlternar }} />);
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled();
  });
});

describe('FormAltaGrupo', () => {
  const rellenar = (nombre: string, club = '') => {
    fireEvent.change(screen.getByLabelText('Nombre del atleta'), { target: { value: nombre } });
    fireEvent.change(screen.getByLabelText('Club'), { target: { value: club } });
  };

  it('envía el nombre y el club recortados y se vacía si sale bien', async () => {
    const onEnviar = vi.fn().mockResolvedValue(undefined);
    render(<FormAltaGrupo onEnviar={onEnviar} />);
    rellenar('  Ana Pérez ', ' Club X ');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Añadir' })); });
    expect(onEnviar).toHaveBeenCalledWith({ nombre: 'Ana Pérez', club: 'Club X' });
    expect(screen.getByLabelText('Nombre del atleta')).toHaveValue('');
    expect(screen.getByLabelText('Club')).toHaveValue('');
  });

  it('conserva lo escrito si el envío falla, y deja volver a intentarlo', async () => {
    const onEnviar = vi.fn().mockRejectedValue(new Error('no'));
    render(<FormAltaGrupo onEnviar={onEnviar} />);
    rellenar('Ana');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Añadir' })); });
    expect(screen.getByLabelText('Nombre del atleta')).toHaveValue('Ana');
    expect(screen.getByRole('button', { name: 'Añadir' })).toBeEnabled();
  });

  it('un nombre en blanco no envía nada', async () => {
    const onEnviar = vi.fn();
    render(<FormAltaGrupo onEnviar={onEnviar} />);
    rellenar('   ');
    await act(async () => { fireEvent.submit(screen.getByRole('button', { name: 'Añadir' }).closest('form')!); });
    expect(onEnviar).not.toHaveBeenCalled();
  });
});

describe('AccesoAdmin', () => {
  const abrir = () => fireEvent.click(screen.getByRole('button', { name: 'Acceso de administrador' }));
  const teclear = (v: string) => fireEvent.change(screen.getByLabelText('Clave de administrador'), { target: { value: v } });
  const entrar = async () => { await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Entrar' })); }); };

  it('el campo de la clave está oculto hasta pulsar el enlace', () => {
    render(<AccesoAdmin sesionIniciada={false} onEntrar={async () => true} onSalir={() => {}} />);
    expect(screen.queryByLabelText('Clave de administrador')).toBeNull();
    abrir();
    expect(screen.getByLabelText('Clave de administrador')).toHaveFocus();
  });

  it('una clave rechazada vacía el campo; si no se pudo comprobar, lo conserva', async () => {
    const onEntrar = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(null);
    render(<AccesoAdmin sesionIniciada={false} onEntrar={onEntrar} onSalir={() => {}} />);
    abrir();
    teclear(' secreta ');
    await entrar();
    expect(onEntrar).toHaveBeenCalledWith('secreta');
    expect(screen.getByLabelText('Clave de administrador')).toHaveValue('');

    teclear('otra');
    await entrar();
    expect(screen.getByLabelText('Clave de administrador')).toHaveValue('otra');
  });

  it('con sesión iniciada el enlace sirve para salir', () => {
    const onSalir = vi.fn();
    render(<AccesoAdmin sesionIniciada onEntrar={async () => true} onSalir={onSalir} />);
    fireEvent.click(screen.getByRole('button', { name: 'Administrador · Salir' }));
    expect(onSalir).toHaveBeenCalledOnce();
    expect(screen.queryByLabelText('Clave de administrador')).toBeNull();
  });
});

describe('ListaGrupo', () => {
  const entradas = [{ id: 'a|c', nombre: 'Ana', club: 'Club', sinCombates: true }];

  it('Quitar se bloquea mientras dura y se libera aunque falle', async () => {
    let rechazar!: (e: Error) => void;
    const onQuitar = vi.fn().mockReturnValue(new Promise((_, r) => { rechazar = r; }));
    render(<ListaGrupo entradas={entradas} onQuitar={onQuitar} />);
    expect(screen.getByText(/Lista del grupo \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText('sin combates todavía')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Quitar' }));
    expect(onQuitar).toHaveBeenCalledWith('a|c');
    expect(screen.getByRole('button', { name: 'Quitar' })).toBeDisabled();

    await act(async () => { rechazar(new Error('no')); });
    expect(screen.getByRole('button', { name: 'Quitar' })).toBeEnabled();
  });

  it('vacía dice que no hay nadie', () => {
    render(<ListaGrupo entradas={[]} onQuitar={() => {}} />);
    expect(screen.getByText('Nadie todavía.')).toBeInTheDocument();
  });
});

describe('PanelDetalle', () => {
  it('cerrado no pinta nada', () => {
    const { container } = render(<PanelDetalle abierto={false} titulo="Ana" onCerrar={() => {}}>x</PanelDetalle>);
    expect(container).toBeEmptyDOMElement();
  });

  it('se cierra con × y al tocar el fondo, pero no al tocar el contenido', () => {
    const onCerrar = vi.fn();
    render(<PanelDetalle abierto titulo="Ana" onCerrar={onCerrar}><p>contenido</p></PanelDetalle>);
    const dialogo = screen.getByRole('dialog', { name: 'Ana' });
    expect(dialogo).toHaveAttribute('aria-modal', 'true');

    fireEvent.click(screen.getByText('contenido'));
    expect(onCerrar).not.toHaveBeenCalled();
    fireEvent.click(dialogo);
    expect(onCerrar).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    expect(onCerrar).toHaveBeenCalledTimes(2);
  });
});

describe('Cabecera', () => {
  it('solo pinta los botones para los que hay acción', () => {
    const { rerender } = render(<Cabecera titulo="FC Team" />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();

    const onVolver = vi.fn();
    const onRecargar = vi.fn();
    rerender(<Cabecera titulo="Open" onVolver={onVolver} onRecargar={onRecargar} enlaceEvento="https://smoothcomp.com/e/1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Volver a los eventos' }));
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar ahora' }));
    expect(onVolver).toHaveBeenCalledOnce();
    expect(onRecargar).toHaveBeenCalledOnce();
    expect(screen.getByRole('link', { name: 'Ver el evento en Smoothcomp' })).toHaveAttribute('href', 'https://smoothcomp.com/e/1');
  });

  it('no enlaza al evento si la dirección no es https', () => {
    render(<Cabecera titulo="Open" enlaceEvento="javascript:alert(1)" />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('la variante «inicio» añade su clase y la normal no', () => {
    const { container, rerender } = render(<Cabecera titulo="FC Team" />);
    expect(container.querySelector('header')).toHaveClass('fc-cabecera');
    expect(container.querySelector('header')).not.toHaveClass('fc-cabecera--inicio');

    rerender(<Cabecera titulo="FC Team" variante="inicio" />);
    expect(container.querySelector('header')).toHaveClass('fc-cabecera', 'fc-cabecera--inicio');

    rerender(<Cabecera titulo="FC Team" variante="normal" />);
    expect(container.querySelector('header')).not.toHaveClass('fc-cabecera--inicio');
  });

  it('si el logo no carga, se quita sin dejar hueco', () => {
    const { container } = render(<Cabecera titulo="FC Team" logo="img/logo.png" />);
    const logo = container.querySelector('img.fc-logo')!;
    expect(logo).toBeInTheDocument();
    fireEvent.error(logo);
    expect(container.querySelector('img.fc-logo')).toBeNull();
  });
});
