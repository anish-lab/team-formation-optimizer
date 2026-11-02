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
  limits: { time_limit: number; node_limit?: number | null; use_coloring: boolean; allow_heuristic: boolean; max_cliques: number }
}
export interface ApiErr { code?: string; message?: string; details?: any }
export type Page = 'home' | 'wizard' | 'results' | 'graph' | 'evaluation' | 'export'
export const defaultSettings: Settings = {
  objective: { alpha: 1, beta: 1, edge_mode: 'hard', threshold: 0.5 },
  team: { policy: 'variable_sizes', preferred_size: 4, num_teams: null, min_size: 4, max_size: 5, strict_team_count: true,
    strict_team_size: false, full_coverage: false, equal_sizes: false, priority: 'coverage_first' },
  limits: { time_limit: 30, node_limit: null, use_coloring: true, allow_heuristic: false, max_cliques: 250000 },
}
