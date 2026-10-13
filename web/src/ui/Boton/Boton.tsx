import type { AnchorHTMLAttributes, ButtonHTMLAttributes, MouseEventHandler } from 'react';
import { clases } from '../clases';
import { esUrlSegura } from '../urlSegura';

export type VarianteBoton = 'pildora' | 'icono' | 'bloque' | 'discontinuo' | 'enlace';

export interface BotonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Forma: pildora (por defecto), icono, bloque, discontinuo o enlace. Cada una se explica en la descripción del componente. */
  variante?: VarianteBoton;
  /** Encendido: relleno con el color del equipo (`pildora`) o borde verde (`discontinuo`). */
  activo?: boolean;
  /** Si se da, se pinta como enlace (`<a>`) que abre en otra pestaña. Solo https://; otra cosa no pinta nada. */
  href?: string;
  /** Al pulsar. */
  onClick?: MouseEventHandler<HTMLButtonElement>;
  /** Bloqueado: no responde y se ve atenuado en `bloque` y `discontinuo`. */
  disabled?: boolean;
  /** `button` por defecto; `submit` para el que envía un formulario. */
  type?: 'button' | 'submit' | 'reset';
  /** Texto emergente. En los botones de solo símbolo, ponle también `aria-label`. */
  title?: string;
  /** Nombre para lectores de pantalla; obligatorio si el botón es solo un símbolo («↻»). */
  'aria-label'?: string;
}

/**
 * Botón táctil de la web. Cinco formas (`variante`) para cinco usos; el color del equipo
 * (`--equipo`) marca el estado `activo`. Con `href` se convierte en enlace externo.
 *
 * Variantes:
 * - `pildora`: acción corta dentro de una tarjeta («Seguir», «Quitar», «Entrar»).
 * - `icono`: círculo de 40 px con un símbolo («‹», «↻», «×»); ponle `aria-label`.
 * - `bloque`: ancho completo, para acciones de página («Cargar más»).
 * - `discontinuo`: ancho completo y borde punteado; acción secundaria que afecta a todo el grupo.
 * - `enlace`: texto subrayado y discreto («Acceso de administrador»).
 */
export function Boton({ variante = 'pildora', activo = false, href, className, type, ...resto }: BotonProps) {
  const clase = clases('fc-boton', `fc-boton--${variante}`, activo && 'fc-boton--activo', className);

  if (href !== undefined) {
    if (!esUrlSegura(href)) return null;
    const { children, ...atributos } = resto;
    return (
      <a
        {...(atributos as AnchorHTMLAttributes<HTMLAnchorElement>)}
        className={clase}
        href={href}
        target="_blank"
        rel="noopener"
      >
        {children}
      </a>
    );
  }

  // `button` por defecto: dentro de un formulario, el que envía lo dice con type="submit".
  return <button {...resto} className={clase} type={type ?? 'button'} />;
}
