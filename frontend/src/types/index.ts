export type FType = 'numeric_continuous' | 'numeric_integer' | 'categorical' | 'binary'
export interface Feature {
  name: string; column: string; type: FType; importance: number; required: boolean
  role: 'value' | 'compat' | 'both' | 'none'; compat_method: 'similarity' | 'complementarity' | 'matrix'
  direction: 'higher_better' | 'lower_better'; min?: number | null; max?: number | null
  categories?: string[] | null; category_values?: Record<string, number> | null; compat_matrix?: Record<string, number> | null
  missing_policy: 'error' | 'impute_mean' | 'impute_median' | 'impute_mode' | 'fill_value'; fill_value?: string | null
}
export interface Settings {
  objective: { alpha: number; beta: number; edge_mode: 'hard' | 'soft'; threshold: number }
  team: {
    policy: string; preferred_size: number; num_teams?: number | null; min_size?: number | null; max_size?: number | null
    strict_team_count: boolean; strict_team_size: boolean; full_coverage: boolean; equal_sizes: boolean; priority: string
  }
  limits: { time_limit: number; node_limit?: number | null; max_cliques: number }
}
export interface ApiErr { code?: string; message?: string; details?: any }
export type Page = 'wizard' | 'results'
