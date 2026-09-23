import type { ApiError, Cluster, GraphResponse, NodeDetail, NodeSummary, SummaryData, TopNode } from './types';

const isDemoMode = (import.meta.env.VITE_DEMO_MODE ?? '').toLowerCase() === 'true';

const getDemoModule = async () => import('./demoData');

async function readJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let payload: Partial<ApiError> = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    const message = payload?.error?.message ?? `HTTP ${response.status}`;
    throw new Error(message);
  }

  return (await response.json()) as T;
}

const toQuery = (params: Record<string, string | number | boolean | undefined>) => {
  const filteredEntries = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '');
  const query = filteredEntries
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&');
  return query ? `?${query}` : '';
};

export const apiClient = {
  async getSummary(): Promise<SummaryData> {
    if (isDemoMode) {
      const demo = await getDemoModule();
      return demo.demoSummary;
    }
    return readJson<SummaryData>(`/api/summary`);
  },

  async getNodes(params?: Partial<Record<string, string | number | boolean | undefined>>): Promise<{ items: NodeSummary[]; total: number }> {
    if (isDemoMode) {
      const demo = await getDemoModule();
      const items = demo.demoNodes.filter((node) => {
        if (params?.gid !== undefined && node.gid !== String(params.gid)) return false;
        if (params?.role !== undefined && node.role !== params.role) return false;
        if (params?.cluster_id !== undefined && node.cluster_id !== Number(params.cluster_id)) return false;
        if (params?.depth !== undefined && node.depth !== Number(params.depth)) return false;
        if (params?.is_seed !== undefined && node.is_seed !== Boolean(params.is_seed)) return false;
        return true;
      });
      return { items, total: items.length };
    }

    const query = toQuery(params ?? {});
    return readJson<{ items: NodeSummary[]; total: number }>(`/api/nodes${query}`);
  },

  async getNodeByGid(gid: string): Promise<NodeDetail | null> {
    if (isDemoMode) {
      const demo = await getDemoModule();
      return demo.demoNodeDetails[gid] ?? null;
    }
    try {
      return await readJson<NodeDetail>(`/api/nodes/${encodeURIComponent(gid)}`);
    } catch (error) {
      if (String((error as Error).message).includes('404')) return null;
      throw error;
    }
  },

  async getGraph(params?: Partial<Record<string, string | number | boolean | undefined>>): Promise<GraphResponse> {
    if (isDemoMode) {
      const demo = await getDemoModule();
      return demo.demoGraph;
    }
    const query = toQuery(params ?? {});
    return readJson<GraphResponse>(`/api/graph${query}`);
  },

  async getTopNodes(limit = 20): Promise<TopNode[]> {
    if (isDemoMode) {
      const demo = await getDemoModule();
      return demo.demoTopNodes.slice(0, Math.min(limit, 20));
    }
    const payload = await readJson<{ items: TopNode[] }>(`/api/top?limit=${limit}`);
    return payload.items;
  },

  async getClusters(): Promise<Cluster[]> {
    if (isDemoMode) {
      const demo = await getDemoModule();
      return demo.demoClusters;
    }
    const payload = await readJson<{ items: Cluster[] }>(`/api/clusters`);
    return payload.items;
  },

  async getCsv(filename: string): Promise<string> {
    if (isDemoMode) {
      const demo = await getDemoModule();
      return demo.exportCsv(filename);
    }
    const response = await fetch(`/api/exports/${encodeURIComponent(filename)}`);
    if (!response.ok) {
      throw new Error(`Не удалось скачать ${filename}`);
    }
    return response.text();
  },
};
