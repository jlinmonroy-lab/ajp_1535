import type { ReactNode } from 'react';
import { Boton } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16, display: 'grid', gap: 12 }}>{children}</div>
);
const Fila = ({ children }: { children: ReactNode }) => (
  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>{children}</div>
);

/** Acciones cortas dentro de una tarjeta: seguir, quitar, entrar. «activo» las rellena con el color del equipo. */
export function Pildora() {
  return (
    <Fondo>
      <Fila>
        <Boton>Seguir</Boton>
        <Boton activo>Siguiendo</Boton>
        <Boton>Quitar</Boton>
        <Boton disabled>Guardando…</Boton>
      </Fila>
    </Fondo>
  );
}

/** Círculos de 40 px con un símbolo; siempre con aria-label porque no tienen texto. */
export function Iconos() {
  return (
    <Fondo>
      <Fila>
        <Boton variante="icono" aria-label="Volver a los eventos">‹</Boton>
        <Boton variante="icono" aria-label="Actualizar ahora">↻</Boton>
        <Boton variante="icono" aria-label="Cerrar">×</Boton>
        <Boton variante="icono" href="https://smoothcomp.com/es/event/33588" aria-label="Ver el evento en Smoothcomp">↗</Boton>
      </Fila>
    </Fondo>
  );
}

/** Acción de página, a todo el ancho: cargar más resultados, y el mismo botón mientras carga. */
export function DeBloque() {
  return (
    <Fondo>
      <Boton variante="bloque">Cargar más</Boton>
      <Boton variante="bloque" disabled>Cargando…</Boton>
    </Fondo>
  );
}

/** «Seguir para todos»: borde punteado hasta que se activa y entonces verde. */
export function Discontinuo() {
  return (
    <Fondo>
      <Boton variante="discontinuo">Seguir para todos</Boton>
      <Boton variante="discontinuo" activo>✓ Lo ve todo el grupo</Boton>
    </Fondo>
  );
}

/** Discreto, al pie de la pantalla de inicio. */
export function ComoEnlace() {
  return (
    <Fondo>
      <div style={{ textAlign: 'center' }}>
        <Boton variante="enlace">Acceso de administrador</Boton>
      </div>
    </Fondo>
  );
}
