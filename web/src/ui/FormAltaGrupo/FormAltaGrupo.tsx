import { useRef, useState, type FormEvent } from 'react';
import { Boton } from '../Boton/Boton';
import { Campo } from '../Campo/Campo';
import { TextoTenue } from '../TextoTenue/TextoTenue';
import { TituloSeccion } from '../TituloSeccion/TituloSeccion';

export interface FormAltaGrupoProps {
  /** Recibe {nombre, club}. Si termina bien se vacía el formulario; si se rechaza, conserva lo escrito. */
  onEnviar: (valores: { nombre: string; club: string }) => Promise<void> | void;
}

/** Formulario para apuntar a mano a un atleta a la lista del grupo (nombre como en Smoothcomp, club opcional). */
export function FormAltaGrupo({ onEnviar }: FormAltaGrupoProps) {
  const [nombre, setNombre] = useState('');
  const [club, setClub] = useState('');
  const [enviando, setEnviando] = useState(false);
  const campoNombre = useRef<HTMLInputElement>(null);

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    const limpio = nombre.trim();
    if (!limpio) return;
    setEnviando(true);
    try {
      await onEnviar({ nombre: limpio, club: club.trim() });
      setNombre('');
      setClub('');
    } catch {
      /* conserva lo escrito: quien lo pasa ya avisó del error */
    } finally {
      setEnviando(false);
      campoNombre.current?.focus();
    }
  }

  return (
    <form className="fc-tarjeta fc-form-grupo" autoComplete="off" onSubmit={enviar}>
      <TituloSeccion>Añadir al grupo</TituloSeccion>
      <Campo
        ref={campoNombre}
        name="nombre"
        type="text"
        required
        placeholder="Nombre y apellidos, como en Smoothcomp"
        aria-label="Nombre del atleta"
        value={nombre}
        onChange={(ev) => setNombre(ev.target.value)}
      />
      <Campo
        name="club"
        type="text"
        placeholder="Club (opcional)"
        aria-label="Club"
        value={club}
        onChange={(ev) => setClub(ev.target.value)}
      />
      <Boton type="submit" activo disabled={enviando}>Añadir</Boton>
      <TextoTenue>Sin club, se le reconoce por el nombre en cualquier club.</TextoTenue>
    </form>
  );
}
