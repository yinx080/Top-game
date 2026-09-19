import type { RoomSummary, Seat } from '../types'

/** Error con el código que manda el backend, para poder reaccionar a él. */
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError('offline', 'No hay conexión con el servidor.', 0)
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const error = body?.error
    throw new ApiError(
      error?.code ?? 'http_error',
      error?.message ?? describeStatus(response.status),
      response.status,
    )
  }
  return (await response.json()) as T
}

function describeStatus(status: number): string {
  if (status === 404) return 'Esa sala ya no existe.'
  if (status === 422) return 'Revisa los datos que has escrito.'
  return 'El servidor no ha podido atender la petición.'
}

export interface ServerConfig {
  minPlayers: number
  maxPlayers: number
  defaultMaxPlayers: number
  limits: { name: number; roomName: number; topic: number; answer: number }
  deck: { minValue: number; maxValue: number }
  sampleTopics: string[]
}

export const api = {
  hotTopics: () => request<{ topics: { text: string; rounds: number }[] }>('/api/hot-topics').then((r) => r.topics),
  config: () => request<ServerConfig>('/api/config'),

  publicRooms: () => request<{ rooms: RoomSummary[] }>('/api/rooms').then((r) => r.rooms),

  searchRooms: (query: string) =>
    request<{ rooms: RoomSummary[] }>(
      `/api/rooms/search?q=${encodeURIComponent(query)}`,
    ).then((r) => r.rooms),

  room: (code: string) => request<RoomSummary>(`/api/rooms/${encodeURIComponent(code)}`),

  createRoom: (body: {
    name: string
    playerName: string
    isPrivate: boolean
    password: string | null
    maxPlayers: number
  }) => request<Seat>('/api/rooms', { method: 'POST', body: JSON.stringify(body) }),

  joinRoom: (code: string, body: { playerName: string; password: string | null }) =>
    request<Seat>(`/api/rooms/${encodeURIComponent(code)}/join`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
