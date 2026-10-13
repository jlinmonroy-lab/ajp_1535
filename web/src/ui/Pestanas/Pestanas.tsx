import { clases } from '../clases';
import { Contador } from '../Contador/Contador';

export interface Pestana {
  /** Identificador estable; es lo que recibe `onCambiar`. */
  id: string;
  etiqueta: string;
  /** Número que se pinta junto a la etiqueta; con `0` o vacío no se pinta burbuja. */
  contador?: number;
}

export interface PestanasProps {
  pestanas: Pestana[];
  /** `id` de la pestaña seleccionada. */
  activa: string;
  onCambiar: (id: string) => void;
  className?: string;
}

/** Barra de pestañas pegada bajo la cabecera, repartidas a partes iguales; la activa se rellena con el color del equipo. */
export function Pestanas({ pestanas, activa, onCambiar, className }: PestanasProps) {
  return (
    <nav className={clases('fc-pestanas', className)} role="tablist">
      {pestanas.map((p) => (
        <button
          key={p.id}
          type="button"
          className={clases('fc-pestana', p.id === activa && 'fc-pestana--activa')}
          data-vista={p.id}
          role="tab"
          aria-selected={p.id === activa}
          onClick={() => onCambiar(p.id)}
        >
          {p.etiqueta}
          {p.contador !== undefined && <>{' '}<Contador id={`contador-${p.id}`}>{p.contador || ''}</Contador></>}
        </button>
      ))}
    </nav>
  );
}
