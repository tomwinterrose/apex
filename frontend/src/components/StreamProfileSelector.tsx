import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { Select } from "@/components/ui/select"
import { cn } from "@/lib/utils"

interface StreamProfile {
  id: number
  name: string
  command: string
}

async function fetchStreamProfiles(): Promise<StreamProfile[]> {
  const response = await fetch("/api/v1/dispatcharr/stream-profiles")
  if (!response.ok) {
    if (response.status === 503) return [] // Dispatcharr not connected
    throw new Error("Failed to fetch stream profiles")
  }
  return response.json()
}

interface StreamProfileSelectorProps {
  /** Currently selected stream profile ID (null = use default/none) */
  value: number | null
  /** Callback when selection changes */
  onChange: (id: number | null) => void
  /** Whether Dispatcharr is connected */
  disabled?: boolean
  /** Optional class name */
  className?: string
  /** Placeholder text for empty selection */
  placeholder?: string
  /** Whether this is for settings (shows "None") or group (shows "Use global default") */
  isGlobalDefault?: boolean
}

/**
 * Stream profile single-select dropdown.
 *
 * Stream profiles define how streams are processed (ffmpeg, VLC, proxy, etc).
 * Unlike channel profiles, this is a single selection - not multi-select.
 */
export function StreamProfileSelector({
  value,
  onChange,
  disabled = false,
  className,
  placeholder,
  isGlobalDefault = false,
}: StreamProfileSelectorProps) {
  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ["dispatcharr-stream-profiles"],
    queryFn: fetchStreamProfiles,
    retry: false,
  })

  if (isLoading) {
    return (
      <div className={cn("flex items-center gap-2 h-10", className)}>
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Loading profiles...</span>
      </div>
    )
  }

  const emptyLabel = isGlobalDefault
    ? "None (Dispatcharr default)"
    : "Use global default"

  return (
    <Select
      value={value?.toString() || ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      disabled={disabled}
      className={className}
    >
      <option value="">{placeholder || emptyLabel}</option>
      {profiles.map((profile) => (
        <option key={profile.id} value={profile.id}>
          {profile.name}
        </option>
      ))}
    </Select>
  )
}
