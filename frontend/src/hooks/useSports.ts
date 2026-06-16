import { useQuery } from "@tanstack/react-query"
import { getSports } from "@/api/teams"

/**
 * Hook to fetch sport display names from the database.
 * Sports are cached with a long stale time since they rarely change.
 *
 * Usage:
 *   const { data } = useSports()
 *   const sportsMap = data?.sports
 *   getSportDisplayName(sport, sportsMap)
 */
export function useSports() {
  return useQuery({
    queryKey: ["sports"],
    queryFn: getSports,
    staleTime: 1000 * 60 * 60, // 1 hour - sports rarely change
  })
}
