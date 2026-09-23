import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { apiClient } from './api/client';
import { roleLabels } from './api/demoData';
import type { Cluster, GraphResponse, NodeDetail, NodeSummary, SummaryData, TopNode } from './api/types';

const roleColors = {
  consolidator: '#4ecdc4',
  transit: '#36a2eb',
  distributor: '#f7b267',
  terminal: '#ff7f7f',
  coordinator: '#ffd166',
  peripheral: '#8aa0b7',
} as const;

const clusterPalette = ['#5eead4', '#7dd3fc', '#c4b5fd', '#f9a8d4', '#fcd34d', '#fca5a5', '#86efac', '#a5b4fc', '#d8b4fe'];

const formatKzt = (value: number) => `${(value / 1000000).toFixed(2)} млн KZT`;
const formatCount = (value: number) => value.toLocaleString('ru-RU');

const getRoleColor = (role: NodeSummary['role']) => roleColors[role] ?? '#8aa0b7';
const getClusterColor = (clusterId: number) => clusterPalette[(clusterId - 1) % clusterPalette.length] ?? '#5eead4';

function App() {
  const graphRef = useRef<HTMLDivElement | null>(null);
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [topNodes, setTopNodes] = useState<TopNode[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [graph, setGraph] = useState<GraphResponse>({ nodes: [], edges: [], scope: 'full', total_nodes: 0, total_edges: 0 });
  const [selectedGid, setSelectedGid] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null);
  const [activeTab, setActiveTab] = useState<'graph' | 'clusters'>('graph');
  const [colorMode, setColorMode] = useState<'role' | 'cluster'>('role');
  const [graphScope, setGraphScope] = useState<'full' | 1 | 2>('full');
  const [filters, setFilters] = useState({
    gid: '',
    role: '',
    cluster_id: '',
    depth: '',
    is_seed: '',
    min_sum_kzt: '0',
  });
  const [status, setStatus] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const isDemoMode = (import.meta.env.VITE_DEMO_MODE ?? '').toLowerCase() === 'true';

  const loadSummary = async () => {
    try {
      const data = await apiClient.getSummary();
      setSummary(data);
    } catch (loadError) {
      setError((loadError as Error).message || 'Ошибка загрузки summary');
    }
  };

  const loadTopNodes = async () => {
    try {
      const items = await apiClient.getTopNodes(20);
      setTopNodes(items);
      if (!selectedGid && items.length > 0) {
        setSelectedGid(items[0].gid);
      }
    } catch (loadError) {
      setError((loadError as Error).message || 'Ошибка загрузки топа');
    }
  };

  const loadClusters = async () => {
    try {
      const items = await apiClient.getClusters();
      setClusters(items);
    } catch (loadError) {
      setError((loadError as Error).message || 'Ошибка загрузки кластеров');
    }
  };

  const loadNodeByGid = async (gid: string) => {
    try {
      const detail = await apiClient.getNodeByGid(gid);
      if (!detail) {
        setSelectedNode(null);
        setError(`Не найден gid ${gid}`);
        return;
      }
      setSelectedNode(detail);
      setStatus(`Найден узел ${gid}`);
    } catch (loadError) {
      setError((loadError as Error).message || `Не удалось загрузить узел ${gid}`);
    }
  };

  const loadGraphData = async () => {
    setLoading(true);
    setError(null);

    try {
      const params: Record<string, string | number | boolean | undefined> = {
        gid: selectedGid ?? undefined,
        role: filters.role || undefined,
        cluster_id: filters.cluster_id || undefined,
        depth: filters.depth || undefined,
        is_seed: filters.is_seed || undefined,
        min_sum_kzt: Number(filters.min_sum_kzt || 0),
      };

      if (graphScope === 'full') {
        delete params.gid;
      } else if (selectedGid) {
        params.gid = selectedGid;
        params.hops = graphScope;
      }

      const response = await apiClient.getGraph(params);
      setGraph(response);
      if (!selectedGid && response.nodes.length > 0) {
        setSelectedGid(response.nodes[0].gid);
      }
    } catch (loadError) {
      setError((loadError as Error).message || 'Ошибка загрузки графа');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSummary();
    void loadTopNodes();
    void loadClusters();
  }, [retryKey]);

  useEffect(() => {
    if (selectedGid) {
      void loadNodeByGid(selectedGid);
    }
  }, [selectedGid]);

  useEffect(() => {
    void loadGraphData();
  }, [selectedGid, graphScope, filters.role, filters.cluster_id, filters.depth, filters.is_seed, filters.min_sum_kzt, retryKey]);

  useEffect(() => {
    if (!graphRef.current || graph.nodes.length === 0) {
      return;
    }

    const cy = cytoscape({
      container: graphRef.current,
      elements: {
        nodes: graph.nodes.map((node) => ({
          data: {
            id: node.gid,
            label: node.gid,
            gid: node.gid,
            role: node.role,
            cluster_id: node.cluster_id,
            selected: node.gid === selectedGid,
            size: 20 + Math.log2(Math.max(node.in_kzt, node.out_kzt, 1) + 1) * 10,
            color: colorMode === 'role' ? getRoleColor(node.role) : getClusterColor(node.cluster_id),
            seed: node.is_seed,
          },
        })),
        edges: graph.edges.map((edge) => ({
          data: {
            id: `${edge.src}-${edge.dst}`,
            source: edge.src,
            target: edge.dst,
            weight: edge.sum_kzt,
          },
        })),
      },
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (element: any) => (colorMode === 'role' ? getRoleColor(element.data('role')) : getClusterColor(element.data('cluster_id'))),
            'width': (element: any) => Math.max(18, Number(element.data('size')) || 20),
            'height': (element: any) => Math.max(18, Number(element.data('size')) || 20),
            'border-width': (element: any) => (element.data('seed') ? 3 : 1),
            'border-color': '#f8fafc',
            'label': 'data(label)',
            'font-size': '10px',
            'color': '#e2e8f0',
            'text-wrap': 'wrap',
            'text-valign': 'center',
            'text-halign': 'center',
            'text-opacity': (element: any) => (element.data('gid') === selectedGid ? 1 : 0),
            'opacity': 0.95,
          },
        },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'line-color': '#58708a',
            'target-arrow-color': '#58708a',
            'width': 1.4,
            'opacity': 0.72,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width': 4,
            'border-color': '#ffffff',
          },
        },
      ],
      layout: {
        name: 'preset',
        fit: true,
        padding: 18,
      },
      zoomingEnabled: true,
      userZoomingEnabled: true,
      panningEnabled: true,
      boxSelectionEnabled: false,
      wheelSensitivity: 0.35,
      minZoom: 0.25,
      maxZoom: 2.5,
    });

    cy.on('tap', 'node', (evt) => {
      const gid = evt.target.data('gid');
      if (gid) {
        setSelectedGid(gid);
      }
    });

    return () => {
      cy.destroy();
    };
  }, [graph, colorMode, selectedGid]);

  const clusterOptions = useMemo(() =>
    clusters.map((cluster) => ({ value: String(cluster.cluster_id), label: `Кластер ${cluster.cluster_id}` })),
    [clusters],
  );

  const nodeCountText = graph.nodes.length > 0 ? `${graph.nodes.length} узлов / ${graph.edges.length} рёбер` : 'Нет данных';

  const handleDownload = async (filename: string) => {
    try {
      const csv = await apiClient.getCsv(filename);
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      setError((downloadError as Error).message || 'Не удалось скачать CSV');
    }
  };

  const resetFilters = () => {
    setFilters({ gid: '', role: '', cluster_id: '', depth: '', is_seed: '', min_sum_kzt: '0' });
    setSelectedGid(topNodes[0]?.gid ?? null);
    setGraphScope('full');
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__title-box">
          <div className="title">Граф денег</div>
          <div className="subtitle">{summary ? `${summary.date_from} — ${summary.date_to}` : 'Период данных'}</div>
        </div>

        <div className="status-box">
          <span className={`status-pill ${isDemoMode ? 'demo' : 'online'}`}>
            {isDemoMode ? 'Демонстрационные данные' : 'API подключено'}
          </span>
          <button type="button" className="ghost-button" onClick={() => setRetryKey((k) => k + 1)}>
            Повторить загрузку
          </button>
        </div>

        <div className="downloads">
          {['nodes_roles.csv', 'clusters.csv', 'top_nodes.csv'].map((file) => (
            <button key={file} type="button" className="action-button" onClick={() => void handleDownload(file)}>
              Скачать {file}
            </button>
          ))}
        </div>
      </header>

      <section className="metrics-grid">
        {[
          ['Узлы', summary ? formatCount(summary.n_nodes) : '—'],
          ['Рёбра', summary ? formatCount(summary.n_edges) : '—'],
          ['Транзакции', summary ? formatCount(summary.n_transactions) : '—'],
          ['Кластеры', summary ? formatCount(summary.n_clusters) : '—'],
          ['Оборот', summary ? formatKzt(summary.total_edge_kzt) : '—'],
        ].map(([label, value]) => (
          <div className="metric-card" key={label}>
            <div className="metric-card__label">{label}</div>
            <div className="metric-card__value">{value}</div>
          </div>
        ))}
      </section>

      {error && <div className="warning-banner">{error}</div>}
      {status && !error && <div className="status-banner">{status}</div>}

      <main className="workspace-grid">
        <aside className="panel panel--left">
          <div className="panel-header">Поиск и фильтры</div>

          <div className="field-group">
            <label htmlFor="gid-search">Поиск gid</label>
            <input
              id="gid-search"
              type="text"
              value={filters.gid}
              placeholder="Введите точный gid"
              onChange={(event) => setFilters((current) => ({ ...current, gid: event.target.value }))}
            />
            <button
              type="button"
              className="action-button action-button--full"
              onClick={() => {
                const value = filters.gid.trim();
                if (!value) {
                  setError('Введите корректный gid для точного поиска');
                  return;
                }
                setSelectedGid(value);
                setGraphScope(1);
              }}
            >
              Искать gid
            </button>
          </div>

          <div className="field-grid">
            <div className="field-group">
              <label htmlFor="role-filter">Роль</label>
              <select id="role-filter" value={filters.role} onChange={(event) => setFilters((current) => ({ ...current, role: event.target.value }))}>
                <option value="">Любая</option>
                {Object.entries(roleLabels).map(([role, label]) => (
                  <option key={role} value={role}>{label}</option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label htmlFor="cluster-filter">Кластер</label>
              <select id="cluster-filter" value={filters.cluster_id} onChange={(event) => setFilters((current) => ({ ...current, cluster_id: event.target.value }))}>
                <option value="">Любой</option>
                {clusterOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label htmlFor="depth-filter">Depth</label>
              <input id="depth-filter" type="number" min="0" max="4" value={filters.depth} onChange={(event) => setFilters((current) => ({ ...current, depth: event.target.value }))} />
            </div>

            <div className="field-group">
              <label htmlFor="seed-filter">Seed</label>
              <select id="seed-filter" value={filters.is_seed} onChange={(event) => setFilters((current) => ({ ...current, is_seed: event.target.value }))}>
                <option value="">Любой</option>
                <option value="true">Да</option>
                <option value="false">Нет</option>
              </select>
            </div>

            <div className="field-group field-group--wide">
              <label htmlFor="min-sum">Мин. сумма ребра, KZT</label>
              <input id="min-sum" type="number" min="0" value={filters.min_sum_kzt} onChange={(event) => setFilters((current) => ({ ...current, min_sum_kzt: event.target.value }))} />
            </div>
          </div>

          <button type="button" className="ghost-button ghost-button--reset" onClick={resetFilters}>Сбросить фильтры</button>

          <div className="top-list">
            <div className="top-list__header">
              <span>Топ-20</span>
              <span>Глобальный рейтинг</span>
            </div>
            <div className="top-list__body">
              {topNodes.map((node) => (
                <button key={node.gid} type="button" className={`top-row ${selectedGid === node.gid ? 'active' : ''}`} onClick={() => { setSelectedGid(node.gid); setGraphScope(1); }}>
                  <span className="top-row__gid">{node.gid}</span>
                  <span className="top-row__role">{roleLabels[node.role]}</span>
                  <span className="top-row__score">{node.priority_score.toFixed(2)}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="panel panel--center">
          <div className="graph-toolbar">
            <div className="segmented-control">
              {['full', 1, 2].map((scope) => (
                <button
                  key={String(scope)}
                  type="button"
                  className={graphScope === scope ? 'active' : ''}
                  onClick={() => setGraphScope(scope as 'full' | 1 | 2)}
                >
                  {scope === 'full' ? 'Вся сеть' : `${scope} шаг`}
                </button>
              ))}
            </div>

            <div className="graph-actions">
              <button type="button" className="ghost-button" onClick={() => graphRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })}>Fit</button>
              <button type="button" className="ghost-button" onClick={() => setSelectedGid(topNodes[0]?.gid ?? null)}>Сброс</button>
            </div>
          </div>

          <div className="legend-box">
            <div className="legend-header">
              <span>Легенда</span>
              <button type="button" className="label-toggle" onClick={() => setColorMode((mode) => (mode === 'role' ? 'cluster' : 'role'))}>
                {colorMode === 'role' ? 'Роли / Кластеры' : 'Кластеры / Роли'}
              </button>
            </div>
            <div className="legend-items">
              {(colorMode === 'role' ? Object.entries(roleColors) : clusterPalette.map((color, index) => [String(index + 1), color] as const)).map(([key, color]) => (
                <span key={String(key)} className="legend-item">
                  <i style={{ background: color }} />
                  {colorMode === 'role' ? roleLabels[key as keyof typeof roleColors] : `Кластер ${key}`}
                </span>
              ))}
            </div>
          </div>

          <div className="graph-panel">
            <div ref={graphRef} className="graph-canvas" />
            {loading && <div className="graph-overlay">Загрузка графа…</div>}
            {!loading && graph.nodes.length === 0 && <div className="graph-overlay">Пустой результат фильтра</div>}
          </div>

          <div className="graph-footer">
            <span>{nodeCountText}</span>
            <span>scope: {graph.scope}</span>
          </div>
        </section>

        <aside className="panel panel--right">
          {selectedNode ? (
            <>
              <div className="panel-header">Карточка узла</div>
              <div className="node-card">
                <div className="node-card__header">
                  <div>
                    <div className="node-card__gid">{selectedNode.node.gid}</div>
                    <div className="node-card__role">{roleLabels[selectedNode.node.role]}</div>
                  </div>
                  <span className="status-pill status-pill--small" style={{ background: getRoleColor(selectedNode.node.role), color: '#07131f' }}>
                    {selectedNode.node.role}
                  </span>
                </div>

                <div className="facts-grid">
                  <div><span>role_score</span><strong>{selectedNode.node.role_score.toFixed(3)}</strong></div>
                  <div><span>priority_score</span><strong>{selectedNode.node.priority_score.toFixed(3)}</strong></div>
                  <div><span>depth</span><strong>{selectedNode.node.depth}</strong></div>
                  <div><span>seed</span><strong>{selectedNode.node.is_seed ? 'Да' : 'Нет'}</strong></div>
                  <div><span>кластер</span><strong>{selectedNode.node.cluster_id}</strong></div>
                  <div><span>плательщики/получатели</span><strong>{selectedNode.node.in_deg}/{selectedNode.node.out_deg}</strong></div>
                  <div><span>входящий оборот</span><strong>{formatKzt(selectedNode.node.in_kzt)}</strong></div>
                  <div><span>исходящий оборот</span><strong>{formatKzt(selectedNode.node.out_kzt)}</strong></div>
                  <div><span>pass_through</span><strong>{selectedNode.node.pass_through === null ? 'Недостаточно данных' : selectedNode.node.pass_through}</strong></div>
                </div>

                <div className="muted-copy">
                  Оценка по правилам, не вероятность виновности.
                </div>

                <div className="detail-block">
                  <h4>Объяснение</h4>
                  <p>{selectedNode.explanation}</p>
                </div>

                <div className="detail-block">
                  <h4>Предупреждения</h4>
                  <ul>
                    {selectedNode.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>

                <div className="detail-block">
                  <h4>Ежедневные потоки</h4>
                  <div className="daily-flows">
                    {selectedNode.daily_flows.map((flow) => (
                      <div key={flow.date} className="daily-flow-row">
                        <span>{flow.date.slice(5)}</span>
                        <div className="bars">
                          <span style={{ width: `${Math.min(100, (flow.in_kzt / 500000) * 100)}%` }} />
                          <span style={{ width: `${Math.min(100, (flow.out_kzt / 500000) * 100)}%` }} className="bars__out" />
                        </div>
                        <small>{flow.in_tx}/{flow.out_tx}</small>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">Выберите узел</div>
          )}
        </aside>
      </main>

      {activeTab === 'clusters' && (
        <section className="panel panel--clusters">
          <div className="panel-header">Кластеры</div>
          <table className="cluster-table">
            <thead>
              <tr>
                <th>Кластер</th>
                <th>Узлы</th>
                <th>Seed</th>
                <th>Внутренний оборот</th>
                <th>Гипотеза</th>
                <th>Переход</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((cluster) => (
                <tr key={cluster.cluster_id}>
                  <td>{cluster.cluster_id}</td>
                  <td>{cluster.n_nodes}</td>
                  <td>{cluster.n_seed}</td>
                  <td>{formatKzt(cluster.sum_kzt_internal)}</td>
                  <td>{cluster.hypothesis}</td>
                  <td>
                    <button type="button" className="ghost-button" onClick={() => { setSelectedGid(cluster.top_gids[0] ?? topNodes[0]?.gid ?? null); setActiveTab('graph'); setGraphScope('full'); }}>
                      Открыть граф
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <nav className="tabbar">
        <button type="button" className={activeTab === 'graph' ? 'active' : ''} onClick={() => setActiveTab('graph')}>Граф</button>
        <button type="button" className={activeTab === 'clusters' ? 'active' : ''} onClick={() => setActiveTab('clusters')}>Кластеры</button>
      </nav>
    </div>
  );
}

export default App;
