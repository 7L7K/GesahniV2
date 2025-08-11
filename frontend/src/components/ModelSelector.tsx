import { useModels } from '@/lib/api'

export function ModelSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data, isLoading, error } = useModels()
  const items = data?.items || []
  const models = items.length > 0 ? items : [
    { engine: 'gpt', name: 'gpt-4o' },
    { engine: 'llama', name: 'llama3' },
  ]
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => onChange('auto')}
        className={value === 'auto' ? 'rounded-md px-3 py-1.5 text-xs bg-primary text-primary-foreground shadow-sm' : 'rounded-md px-3 py-1.5 text-xs hover:bg-accent'}
      >
        auto
      </button>
      {models.map((m) => (
        <button
          key={`${m.engine}:${m.name}`}
          type="button"
          onClick={() => onChange(m.name)}
          className={value === m.name ? 'rounded-md px-3 py-1.5 text-xs bg-primary text-primary-foreground shadow-sm' : 'rounded-md px-3 py-1.5 text-xs hover:bg-accent'}
        >
          {m.name}
        </button>
      ))}
    </div>
  )
}


