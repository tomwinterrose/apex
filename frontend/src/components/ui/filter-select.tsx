import * as React from "react"
import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"

export interface FilterSelectOption {
  value: string
  label: string
}

export interface FilterSelectProps {
  value: string
  onChange: (value: string) => void
  options: FilterSelectOption[]
  placeholder?: string
  className?: string
}

export function FilterSelect({
  value,
  onChange,
  options,
  placeholder = "All",
  className,
}: FilterSelectProps) {
  const [isOpen, setIsOpen] = React.useState(false)
  const containerRef = React.useRef<HTMLDivElement>(null)

  // Close on outside click
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  // Close on escape
  React.useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false)
    }
    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [])

  const selectedOption = options.find((opt) => opt.value === value)
  const isPlaceholder = !selectedOption || selectedOption.value === ""
  const displayValue = selectedOption?.label || placeholder

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex items-center justify-between w-full",
          "h-[18px] px-1 text-[0.65rem] italic",
          "bg-background text-muted-foreground",
          "border border-border rounded-sm",
          "cursor-pointer hover:border-muted-foreground/50",
          "focus:outline-none focus:ring-1 focus:ring-ring"
        )}
      >
        <span className={cn("truncate", isPlaceholder && "text-[0.6rem] opacity-60")}>{displayValue}</span>
        <ChevronDown className={cn("h-2.5 w-2.5 ml-0.5 opacity-50 transition-transform", isOpen && "rotate-180")} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div
          className={cn(
            "absolute z-50 mt-1 min-w-full w-max",
            "bg-card border border-border rounded shadow-lg",
            "max-h-48 overflow-y-auto"
          )}
        >
          {options.map((option) => (
            <div
              key={option.value}
              onClick={() => {
                onChange(option.value)
                setIsOpen(false)
              }}
              className={cn(
                "px-1.5 py-0.5 text-[0.65rem] italic cursor-pointer",
                "hover:bg-secondary",
                option.value === value
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground"
              )}
            >
              {option.label}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
