import { useId, type ReactNode } from 'react';
import { Boton } from '../Boton/Boton';

export interface PanelDetalleProps {
  abierto: boolean;
  /** Título del panel (el nombre del atleta). */
  titulo: string;
  /** Se llama al pulsar «×» o al tocar fuera del panel. */
  onCerrar: () => void;
  children?: ReactNode;
}

/**
 * Hoja modal que sube desde abajo en el móvil (centrada en pantallas anchas) con el detalle de
 * algo: título, botón de cerrar y contenido con scroll. Tocar el fondo oscuro la cierra.
 */
export function PanelDetalle({ abierto, titulo, onCerrar, children }: PanelDetalleProps) {
  const idTitulo = useId();
  if (!abierto) return null;

  return (
    <div
      className="fc-detalle"
      role="dialog"
      aria-modal="true"
      aria-labelledby={idTitulo}
      onClick={(ev) => { if (ev.target === ev.currentTarget) onCerrar(); }}
    >
      <div className="fc-detalle-caja">
        <header className="fc-detalle-cabecera">
          <h2 id={idTitulo}>{titulo}</h2>
          <Boton variante="icono" aria-label="Cerrar" onClick={onCerrar}>&times;</Boton>
        </header>
        <div>{children}</div>
      </div>
    </div>
  );
}
