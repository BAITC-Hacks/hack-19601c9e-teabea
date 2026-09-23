export type Role =
  | 'consolidator'
  | 'transit'
  | 'distributor'
  | 'terminal'
  | 'coordinator'
  | 'peripheral';

export interface NodeSummary {
  gid: string;
  role: Role;
  role_score: number;
  cluster_id: number;
  priority_score: number;
  evidence: string;
  depth: number;
  is_seed: boolean;
  truncated_by_depth: boolean;
  in_deg: number;
  out_deg: number;
  in_kzt: number;
  out_kzt: number;
  in_tx: number;
  out_tx: number;
  pagerank: number;
  pass_through: number | null;
}

export interface Edge {
  src: string;
  dst: string;
  sum_kzt: number;
  n_tx: number;
  depth: number;
}

export interface Cluster {
  cluster_id: number;
  n_nodes: number;
  n_seed: number;
  sum_kzt_internal: number;
  top_gids: string[];
  hypothesis: string;
}

export interface TopNode {
  rank: number;
  gid: string;
  role: Role;
  priority_score: number;
  why: string;
}

export interface SummaryData {
  n_nodes: number;
  n_edges: number;
  n_transactions: number;
  n_seed: number;
  n_clusters: number;
  n_truncated: number;
  total_edge_kzt: number;
  date_from: string;
  date_to: string;
  pipeline_seconds: number;
  warnings: string[];
}

export interface DailyFlow {
  date: string;
  in_kzt: number;
  out_kzt: number;
  in_tx: number;
  out_tx: number;
}

export interface NodeDetail {
  node: NodeSummary;
  explanation: string;
  warnings: string[];
  daily_flows: DailyFlow[];
}

export interface GraphResponse {
  nodes: NodeSummary[];
  edges: Edge[];
  scope: 'full' | 'neighborhood';
  total_nodes: number;
  total_edges: number;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
  };
}
