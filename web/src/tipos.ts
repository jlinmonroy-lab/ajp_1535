/* Forma de los datos que sirve el servidor (y el data.json del modo estático). Los nombres
   en inglés son los de la API (scraper/parse.py y scraper/eventos.py); aquí solo se tipan,
   no se renombran. */

export type MedallaDato = 'gold' | 'silver' | 'bronze';

export interface LadoCombate {
  athleteId: string;
  registrationId: string;
  name: string | null;
  club: string | null;
  country: string | null;
  image: string | null;
  isWinner: boolean;
}

export interface CategoriaCombate {
  raw: string | null;
}

/** `state` es 'running' | 'finished' o, mientras no ha empezado, cualquier otro valor. */
export interface Combate {
  id: string;
  eventId: string;
  eventLabel: string | null;
  bracketId: string | null;
  bracketUrl: string | null;
  mat: string | null;
  round: string | null;
  category: CategoriaCombate;
  estimatedStart: string | null;
  day: string | null;
  state: string | null;
  wonBy: string | null;
  sides: LadoCombate[];
}

export interface MedallaGanada {
  bracketId: string;
  eventId: string;
  category: string | null;
  medal: MedallaDato;
}

export interface Cuadro {
  id: string;
  category: string | null;
  eventLabel: string | null;
  url: string;
}

export interface Atleta {
  id: string;
  events: string[];
  name: string;
  club: string | null;
  country: string | null;
  image: string | null;
  categories: string[];
  brackets: Cuadro[];
  matchIds: string[];
  medals: MedallaGanada[];
  bestMedal: MedallaDato | null;
  inGroup?: boolean;
}

export interface EventoDatos {
  id: string;
  label: string | null;
  name: string | null;
  url?: string;
  baseUrl?: string;
  startdate?: string;
  enddate?: string;
  city?: string;
  country?: string;
  /** Lo añade el servidor: false si el organizador aún no ha publicado el schedule. */
  published?: boolean;
}

export interface Tatami {
  key: string;
  name: string | null;
}

export interface Retransmision {
  mat: string;
  url: string;
}

/** Una persona apuntada a la lista del grupo. */
export interface EntradaGrupo {
  id: string;
  name: string;
  club?: string | null;
}

export interface Datos {
  events: EventoDatos[];
  group?: { name?: string | null; athletes?: EntradaGrupo[] };
  fetchedAt: string;
  stale: boolean;
  staleSince: string | null;
  mats: Tatami[];
  streams?: Retransmision[];
  matches: Combate[];
  athletes: Atleta[];
}

/** Respuesta de POST …/grupo: la lista tal como queda. */
export interface GrupoPanel {
  nombre?: string;
  atletas: EntradaGrupo[];
}

/** Un evento de la búsqueda (GET api/events/search). */
export interface EventoBuscado {
  id: string;
  title: string;
  url: string | null;
  baseUrl?: string | null;
  startdate: string | null;
  enddate: string | null;
  city: string | null;
  country: string | null;
  ended?: boolean;
}

export interface RespuestaBusqueda {
  events: EventoBuscado[];
  page: number;
  hasMore: boolean;
  stale: boolean;
}

/** GET api/config. */
export interface ConfigWeb {
  teamName: string;
  logo: string;
  zona?: { nombre?: string } | null;
  /** El servidor tiene clave de administrador: la web ofrece entrar con ella. */
  admin?: boolean;
  /** El commit desplegado en el servidor (`GIT_SHA`), o "dev". */
  version?: string;
}
