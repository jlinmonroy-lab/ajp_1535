import type { ChangeEventHandler, ComponentPropsWithRef } from 'react';
import { clases } from '../clases';

export interface CampoProps extends ComponentPropsWithRef<'input'> {
  /** Nombre del campo en el formulario. */
  name?: string;
  /** `text` por defecto; `password` para la clave. */
  type?: string;
  /** Valor actual (campo controlado). */
  value?: string;
  /** Al escribir. */
  onChange?: ChangeEventHandler<HTMLInputElement>;
  /** Pista que se ve mientras está vacío. */
  placeholder?: string;
  /** Obligatorio para enviar el formulario. */
  required?: boolean;
  disabled?: boolean;
  /** Nombre para lectores de pantalla; ponlo siempre si no hay una etiqueta visible. */
  'aria-label'?: string;
  /** `off` para que el navegador no sugiera valores. */
  autoComplete?: string;
}

/** Campo de texto de formulario a todo el ancho (nombre, club, clave). Es un `input` normal; admite `ref`. */
export function Campo({ className, ...resto }: CampoProps) {
  return <input {...resto} className={clases('fc-campo', className)} />;
}
