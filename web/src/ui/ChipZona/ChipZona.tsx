import { clases } from '../clases';

export interface ChipZonaProps {
  /** Nombre del lugar por defecto («Madrid, España»). */
  nombre: string;
  /** Encendido: la lista está filtrada por ese lugar. Apagado: sigue a la vista para volver a encenderlo. */
  activo: boolean;
  onAlternar: () => void;
}

/**
 * Chip del filtro de lugar por defecto. Encendido es un chip sólido con el color del equipo y
 * una ✕; apagado se queda discontinuo y a la vista para volver a encenderlo.
 */
export function ChipZona({ nombre, activo, onAlternar }: ChipZonaProps) {
  return (
    <button
      type="button"
      className={clases('fc-chip-zona', activo && 'fc-chip-zona--activo')}
      aria-pressed={activo}
      title="Quitar o poner el filtro de lugar"
      onClick={onAlternar}
    >
      📍 {nombre}{activo ? ' ✕' : ''}
    </button>
  );
}
