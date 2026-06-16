import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import type { TeamAlias, TeamAliasCreate, TeamAliasListResponse } from "./types"

const API_BASE = "/api/v1/aliases"

// Fetch all aliases
export function useAliases(league?: string) {
  return useQuery<TeamAliasListResponse>({
    queryKey: ["aliases", league],
    queryFn: async () => {
      const url = league ? `${API_BASE}?league=${encodeURIComponent(league)}` : API_BASE
      const res = await fetch(url)
      if (!res.ok) throw new Error("Failed to fetch aliases")
      return res.json()
    },
  })
}

// Create alias
export function useCreateAlias() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: TeamAliasCreate) => {
      const res = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
      if (!res.ok) {
        const error = await res.json()
        throw new Error(error.detail || "Failed to create alias")
      }
      return res.json() as Promise<TeamAlias>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aliases"] })
    },
  })
}

// Delete alias
export function useDeleteAlias() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(`${API_BASE}/${id}`, { method: "DELETE" })
      if (!res.ok) throw new Error("Failed to delete alias")
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aliases"] })
    },
  })
}

// Export aliases
export async function exportAliases(): Promise<TeamAliasCreate[]> {
  const res = await fetch(`${API_BASE}/export`)
  if (!res.ok) throw new Error("Failed to export aliases")
  return res.json()
}

// Import aliases
export function useImportAliases() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (aliases: TeamAliasCreate[]) => {
      const res = await fetch(`${API_BASE}/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aliases }),
      })
      if (!res.ok) throw new Error("Failed to import aliases")
      return res.json() as Promise<{ created: number; skipped: number; total: number }>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aliases"] })
    },
  })
}
