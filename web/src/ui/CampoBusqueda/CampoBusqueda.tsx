import type { ChangeEventHandler, ComponentPropsWithRef } from 'react';
import { clases } from '../clases';

export interface CampoBusquedaProps extends Omit<ComponentPropsWithRef<'input'>, 'type'> {
  /** Texto buscado (campo controlado). */
  value?: string;
  /** Al escribir. */
  onChange?: ChangeEventHandler<HTMLInputElement>;
  /** Pista que se ve mientras está vacío («Nombre, club o categoría…»). */
  placeholder?: string;
  /** Nombre para lectores de pantalla («Buscar atleta»); ponlo siempre. */
  'aria-label'?: string;
  /** Máximo de caracteres. */
  maxLength?: number;
}

/**
 * Campo de búsqueda a todo el ancho, con el teclado de búsqueda en el móvil. Es un `input`
 * normal: controla su valor con `value`/`onChange`, admite `ref` y ponle siempre `aria-label`.
 */
export function CampoBusqueda({ className, ...resto }: CampoBusquedaProps) {
  return (
    <input
      inputMode="search"
      autoComplete="off"
      {...resto}
      type="search"
      className={clases('fc-campo-busqueda', className)}
    />
  );
}
