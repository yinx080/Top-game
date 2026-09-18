/** Espejo en TypeScript de lo que envía `backend/app/views.py`. */

export type Phase = 'lobby' | 'proposing' | 'voting' | 'placing' | 'revealing' | 'result'

export interface Card {
  code: string
  rank: string
  suit: 'S' | 'H' | 'D' | 'C'
  value: number
}

export interface PlayerView {
  id: string
  name: string
  color: number
  connected: boolean
  isHost: boolean
  inRound: boolean
  hasCard: boolean
  hasPlaced: boolean
  proposed: boolean
  voted: boolean
  isCurrent: boolean
}

export interface SelfView {
  id: string
  name: string
  color: number
  isHost: boolean
  inRound: boolean
  hasPlaced: boolean
  card: Card | null
  proposed: boolean
  proposal: string | null
  vote: string | null
  isCurrent: boolean
}

export interface CandidateView {
  id: string
  text: string
  author: string | null
  isMine: boolean
  isRandom: boolean
  voters: string[]
}

export interface TableEntry {
  slot: number
  playerId: string
  playerName: string
  color: number
  answer: string
  revealed: boolean
  card: Card | null
}

export interface RoomView {
  code: string
  name: string
  isPrivate: boolean
  hostId: string
  phase: Phase
  round: number
  maxPlayers: number
  minPlayers: number
  players: PlayerView[]
  you: SelfView | null
  topic: { text: string; author: string | null } | null
  candidates: CandidateView[]
  pendingProposals: string[]
  pendingVotes: string[]
  turnOrder: string[]
  turnIndex: number
  currentPlayerId: string | null
  table: TableEntry[]
  revealIndex: number
  outcome: 'win' | 'lose' | null
  breakIndex: number | null
  savedTopics: number
  limits: {
    answer: number
    topic: number
    name: number
    minValue: number
    maxValue: number
  }
}

export interface RoomSummary {
  code: string
  name: string
  isPrivate: boolean
  players: number
  online: number
  maxPlayers: number
  phase: Phase
  inGame: boolean
  round: number
  createdAt: number
}

export interface Seat {
  code: string
  playerId: string
  token: string
  room: RoomSummary
}

export type ServerEvent =
  | { kind: 'player_online'; name: string }
  | { kind: 'player_offline'; name: string }
  | { kind: 'player_left'; name: string }
  | { kind: 'round_started'; round: number }
  | { kind: 'proposal_sent' }
  | { kind: 'voting_open' }
  | { kind: 'vote_cast' }
  | { kind: 'topic_chosen'; topic: string }
  | { kind: 'card_placed'; slot: number }
  | { kind: 'turn_skipped' }
  | { kind: 'reveal_start' }
  | { kind: 'reveal'; slot: number }
  | { kind: 'result'; outcome: 'win' | 'lose' }
  | { kind: 'round_aborted' }
  | { kind: 'back_to_lobby' }
  | { kind: 'players_changed' }

export type ServerMessage =
  | { type: 'welcome'; playerId: string; code: string }
  | { type: 'state'; room: RoomView; event?: ServerEvent }
  | { type: 'error'; code: string; message: string }
  | { type: 'pong' }

export type ClientMessage =
  | { action: 'ping' }
  | { action: 'leave' }
  | { action: 'start_round' }
  | { action: 'next_round' }
  | { action: 'propose'; text: string | null }
  | { action: 'vote'; candidateId: string }
  | { action: 'place'; slot: number; answer: string }
  | { action: 'force' }
  | { action: 'skip_turn' }
  | { action: 'back_to_lobby' }
  | { action: 'kick'; playerId: string }
