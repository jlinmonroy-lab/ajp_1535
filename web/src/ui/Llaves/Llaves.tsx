import { EnlaceExterno } from '../EnlaceExterno/EnlaceExterno';
import { esUrlSegura } from '../urlSegura';

export interface Llave {
  /** Dirección del cuadro en Smoothcomp (`https://…`). Las que no lo sean se descartan. */
  url: string;
  /** Texto del enlace: «Ver llave», o la categoría si el atleta tiene más de un cuadro. */
  texto: string;
}

export interface LlavesProps {
  llaves: Llave[];
}

/** Fila de enlaces a los cuadros (llaves) de un atleta en Smoothcomp; no pinta nada si no hay ninguno válido. */
export function Llaves({ llaves }: LlavesProps) {
  const validas = llaves.filter((l) => esUrlSegura(l.url));
  if (!validas.length) return null;
  return (
    <div className="fc-llaves">
      {validas.map((l) => (
        <EnlaceExterno key={l.url} href={l.url} title="Ver la llave en Smoothcomp">
          ⤢ {l.texto}
        </EnlaceExterno>
      ))}
    </div>
  );
}
