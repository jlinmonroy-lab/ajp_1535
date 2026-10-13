/* La lista de la pestaña «Buscar»: los atletas cuyo nombre, club o categoría contienen lo escrito.
 *
 * Es un componente propio, y no una función de Evento, para que quede dentro del LimiteError: si
 * una ficha viene rota, falla esta lista y no toda la pantalla.
 */
import type { ReactNode } from 'react';
import type { Atleta, Datos } from '../tipos';
import { TextoTenue, Vacio } from '../ui';
import { normalizar } from './util';

const MIN_LETRAS = 2;
const MAX_RESULTADOS = 60;

interface Props {
  datos: Datos;
  consulta: string;
  /** El aviso de «schedule sin publicar»: si lo hay, sustituye a los mensajes de «nada que enseñar». */
  aviso: ReactNode;
  tarjeta: (atleta: Atleta) => ReactNode;
}

export function ResultadosBusqueda({ datos, consulta, aviso, tarjeta }: Props) {
  const q = normalizar(consulta.trim());
  if (q.length < MIN_LETRAS) return aviso || <Vacio>Escribe al menos dos letras.</Vacio>;

  // `categories` no se da por hecho: una ficha incompleta no debe tumbar la búsqueda de todos.
  const encontrados = datos.athletes.filter((a) =>
    normalizar(a.name).includes(q) ||
    normalizar(a.club).includes(q) ||
    (a.categories ?? []).some((c) => normalizar(c).includes(q)));

  if (!encontrados.length) return aviso || <Vacio>Ningún atleta coincide.</Vacio>;

  return (
    <>
      <TextoTenue>{encontrados.length} resultado(s)</TextoTenue>
      {encontrados.slice(0, MAX_RESULTADOS).map((a) => tarjeta(a))}
    </>
  );
}
