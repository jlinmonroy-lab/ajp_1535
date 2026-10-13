import { clases } from '../clases';

export interface OpcionFiltro {
  /** Identificador estable; es lo que recibe `onCambiar`. */
  id: string;
  etiqueta: string;
}

export interface FiltrosProps {
  opciones: OpcionFiltro[];
  /** `id` de la opción seleccionada. */
  valor: string;
  onCambiar: (id: string) => void;
  /** Nombre del grupo para lectores de pantalla («Cuándo»). */
  etiqueta?: string;
}

/** Grupo de píldoras excluyentes para acotar una lista («Próximos», «Pasados», «Todos»); la elegida se rellena con el color del equipo. */
export function Filtros({ opciones, valor, onCambiar, etiqueta }: FiltrosProps) {
  return (
    <div className="fc-filtros" role="group" aria-label={etiqueta}>
      {opciones.map((o) => (
        <button
          key={o.id}
          type="button"
          className={clases('fc-filtro', o.id === valor && 'fc-filtro--activo')}
          data-cuando={o.id}
          aria-pressed={o.id === valor}
          onClick={() => onCambiar(o.id)}
        >
          {o.etiqueta}
        </button>
      ))}
    </div>
  );
}
