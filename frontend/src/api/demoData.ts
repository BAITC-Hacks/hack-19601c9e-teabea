import type { Cluster, DailyFlow, GraphResponse, NodeDetail, NodeSummary, SummaryData, TopNode } from './types';

export const roleLabels: Record<string, string> = {
  consolidator: 'Консолидация',
  transit: 'Транзит',
  distributor: 'Распределение',
  terminal: 'Возможный конечный получатель',
  coordinator: 'Координация, гипотеза',
  peripheral: 'Периферия',
};

const summaryData: SummaryData = {
  n_nodes: 2248,
  n_edges: 3119,
  n_transactions: 4840,
  n_seed: 81,
  n_clusters: 9,
  n_truncated: 444,
  total_edge_kzt: 365890012,
  date_from: '2026-07-01',
  date_to: '2026-07-31',
  pipeline_seconds: 42,
  warnings: ['Цвета и сетка обновлены по правилам роли; верификация на реальном API требуется на рабочем бэкенде.'],
};

const nodeSeedList = [
  '1000001', '1000002', '1000003', '1000004', '1000005', '1000006', '1000007', '1000008', '1000009', '1000010',
  '1000011', '1000012', '1000013', '1000014', '1000015', '1000016', '1000017', '1000018', '1000019', '1000020',
  '1000021', '1000022', '1000023', '1000024', '1000025', '1000026', '1000027', '1000028', '1000029', '1000030',
  '1000031', '1000032', '1000033', '1000034', '1000035', '1000036', '1000037', '1000038', '1000039', '1000040',
  '1000041', '1000042', '1000043', '1000044', '1000045', '1000046', '1000047', '1000048', '1000049', '1000050',
  '1000051', '1000052', '1000053', '1000054', '1000055', '1000056', '1000057', '1000058', '1000059', '1000060',
  '1000061', '1000062', '1000063', '1000064', '1000065', '1000066', '1000067', '1000068', '1000069', '1000070',
  '1000071', '1000072', '1000073', '1000074', '1000075', '1000076', '1000077', '1000078', '1000079', '1000080',
  '1000081',
];

const roleOrder: Array<NodeSummary['role']> = ['consolidator', 'transit', 'distributor', 'terminal', 'coordinator', 'peripheral'];

function makeNode(gid: string, role: NodeSummary['role'], priority: number, cluster: number, depth: number, isSeed = false): NodeSummary {
  const outKzt = Math.round((priority + 0.4) * 1820000 + Number(gid.slice(-2)) * 2500);
  const inKzt = Math.round((priority + 0.25) * 1500000 + Number(gid.slice(-3)) * 2000);

  return {
    gid,
    role,
    role_score: Number((0.42 + priority * 0.58).toFixed(4)),
    cluster_id: cluster,
    priority_score: Number(priority.toFixed(4)),
    evidence: isSeed
      ? 'Seed с поэтапным исходящим потоком и устойчивой связью с кластером.'
      : 'Структурные признаки, оборот на ребре и настраиваемые пороги роли.',
    depth,
    is_seed: isSeed,
    truncated_by_depth: depth === 4 && role === 'terminal',
    in_deg: isSeed ? 2 : Math.max(1, Math.round(priority * 10 + 1)),
    out_deg: isSeed ? 5 : Math.max(1, Math.round(priority * 8 + 2)),
    in_kzt: inKzt,
    out_kzt: outKzt,
    in_tx: isSeed ? 4 : Math.max(1, Math.round(priority * 25 + 4)),
    out_tx: isSeed ? 9 : Math.max(1, Math.round(priority * 22 + 3)),
    pagerank: Number((0.02 + priority * 0.27).toFixed(4)),
    pass_through: isSeed ? null : Number((priority * 0.55).toFixed(3)),
  };
}

const nodes: NodeSummary[] = [
  makeNode('1000001', 'consolidator', 0.94, 1, 1, true),
  makeNode('1000002', 'transit', 0.89, 1, 2, true),
  makeNode('1000003', 'distributor', 0.85, 2, 1, true),
  makeNode('1000004', 'terminal', 0.81, 2, 4, false),
  makeNode('1000005', 'coordinator', 0.91, 3, 2, false),
  makeNode('1000006', 'peripheral', 0.49, 3, 3, false),
  makeNode('1000007', 'transit', 0.76, 1, 2, false),
  makeNode('1000008', 'distributor', 0.72, 4, 3, false),
  makeNode('1000009', 'consolidator', 0.67, 4, 1, false),
  makeNode('1000010', 'terminal', 0.62, 5, 4, false),
  makeNode('1000011', 'transit', 0.69, 5, 2, false),
  makeNode('1000012', 'peripheral', 0.38, 5, 1, false),
  makeNode('1000013', 'coordinator', 0.83, 6, 1, false),
  makeNode('1000014', 'distributor', 0.7, 6, 2, false),
  makeNode('1000015', 'terminal', 0.57, 7, 4, false),
  makeNode('1000016', 'peripheral', 0.34, 7, 3, false),
  makeNode('1000017', 'transit', 0.6, 8, 2, false),
  makeNode('1000018', 'distributor', 0.61, 8, 1, false),
  makeNode('1000019', 'consolidator', 0.66, 9, 1, false),
  makeNode('1000020', 'coordinator', 0.78, 9, 1, false),
];

export const demoNodes = nodes;

export const demoTopNodes: TopNode[] = [
  { rank: 1, gid: '1000001', role: 'consolidator', priority_score: 0.94, why: 'Собирает потоки от 7 входящих маршрутов и дублирует их в 3 исходящих канала.' },
  { rank: 2, gid: '1000005', role: 'coordinator', priority_score: 0.91, why: 'Наблюдается высокая связность и синхронный оборот по нескольким узлам кластера.' },
  { rank: 3, gid: '1000002', role: 'transit', priority_score: 0.89, why: 'Похоже, что после сбора средства сразу переправляются дальше через несколько адресов.' },
  { rank: 4, gid: '1000031', role: 'distributor', priority_score: 0.87, why: 'Среди соседей много получателей с низкими суммами и высокой частотой транзакций.' },
  { rank: 5, gid: '1000003', role: 'distributor', priority_score: 0.85, why: 'Формирует веер распределения на широкую выборку получателей.' },
  { rank: 6, gid: '1000013', role: 'coordinator', priority_score: 0.83, why: 'Удерживает несколько узлов в одном кластере и сохраняет структуру маршрута.' },
  { rank: 7, gid: '1000004', role: 'terminal', priority_score: 0.81, why: 'На глубине 4 без исходящих признаков: возможный конечный получатель, но наблюдение обрезано.' },
  { rank: 8, gid: '1000019', role: 'consolidator', priority_score: 0.78, why: 'Регулярная аккумуляция средств с переводом в узел с более высокой ролью.' },
  { rank: 9, gid: '1000011', role: 'transit', priority_score: 0.76, why: 'Обход на второй шаг и быстрый возврат средств в соседний кластер.' },
  { rank: 10, gid: '1000014', role: 'distributor', priority_score: 0.72, why: 'Много исходящих маршрутов и заметный показатель pass_through.' },
  { rank: 11, gid: '1000018', role: 'distributor', priority_score: 0.69, why: 'Жёсткая расслоённость на несколько получателей и невысокая задержка на маршруте.' },
  { rank: 12, gid: '1000020', role: 'coordinator', priority_score: 0.66, why: 'Узел структурирует несколько веток и усиливает внутреннюю связанность кластера.' },
  { rank: 13, gid: '1000009', role: 'consolidator', priority_score: 0.64, why: 'Объединяет несколько поставщиков, но уходит в локальную сеть без прямой видимой экспозиции.' },
  { rank: 14, gid: '1000010', role: 'terminal', priority_score: 0.62, why: 'Поток входит, но дальнейший расход не виден из-за глубины наблюдения.' },
  { rank: 15, gid: '1000017', role: 'transit', priority_score: 0.6, why: 'Малый баланс и высокое число переходов по соседним аккаунтам.' },
  { rank: 16, gid: '1000015', role: 'terminal', priority_score: 0.57, why: 'Сильный входящий поток и нулевой исходящий маршрут, но с обрезкой по глубине.' },
  { rank: 17, gid: '1000018', role: 'distributor', priority_score: 0.53, why: 'Сложная многоступенчатая рассылка и высокая смена получателей.' },
  { rank: 18, gid: '1000041', role: 'transit', priority_score: 0.51, why: 'Много частных переводов, но без стабильной локальной консолидации.' },
  { rank: 19, gid: '1000045', role: 'peripheral', priority_score: 0.47, why: 'Большой входящий поток, но слабые признаки дальнейшего распределения.' },
  { rank: 20, gid: '1000051', role: 'distributor', priority_score: 0.45, why: 'Наблюдается широкий веер на последние шаги, но низкая валидность в global view.' },
];

const clusterData: Cluster[] = [
  { cluster_id: 1, n_nodes: 274, n_seed: 20, sum_kzt_internal: 42350000, top_gids: ['1000001', '1000002', '1000007'], hypothesis: 'Потоки пересекаются в узлах консолидации с последующим транзитом.' },
  { cluster_id: 2, n_nodes: 188, n_seed: 14, sum_kzt_internal: 28850000, top_gids: ['1000003', '1000004'], hypothesis: 'Веерное распределение на несколько получателей с ограниченной глубиной.' },
  { cluster_id: 3, n_nodes: 211, n_seed: 11, sum_kzt_internal: 31420000, top_gids: ['1000005', '1000006'], hypothesis: 'Координация вокруг ключевого узла с периферийными связями.' },
  { cluster_id: 4, n_nodes: 163, n_seed: 9, sum_kzt_internal: 22130000, top_gids: ['1000008', '1000009'], hypothesis: 'Локальное накопление средств и последующее распределение внутри кластера.' },
  { cluster_id: 5, n_nodes: 201, n_seed: 10, sum_kzt_internal: 25680000, top_gids: ['1000010', '1000011', '1000012'], hypothesis: 'Сильное влияние на терминальные узлы и обрезание сети по глубине.' },
  { cluster_id: 6, n_nodes: 243, n_seed: 7, sum_kzt_internal: 29890000, top_gids: ['1000013', '1000014'], hypothesis: 'Межкластерная связь с выраженной координацией и перераспределением.' },
  { cluster_id: 7, n_nodes: 142, n_seed: 5, sum_kzt_internal: 17610000, top_gids: ['1000015', '1000016'], hypothesis: 'Небольшой кластер на поздних шагах, вероятно, периферийная сеть.' },
  { cluster_id: 8, n_nodes: 127, n_seed: 3, sum_kzt_internal: 14370000, top_gids: ['1000017', '1000018'], hypothesis: 'Переход через распределительные узлы в несколько адресатов.' },
  { cluster_id: 9, n_nodes: 179, n_seed: 2, sum_kzt_internal: 19850000, top_gids: ['1000019', '1000020'], hypothesis: 'Высокие связи и высокая роль в структурном интересе относительно соседей.' },
];

const edgePairs: Array<[string, string, number, number, number]> = [
  ['1000001', '1000002', 2480000, 12, 1],
  ['1000001', '1000007', 1830000, 9, 1],
  ['1000002', '1000005', 2240000, 11, 2],
  ['1000002', '1000007', 1980000, 7, 2],
  ['1000003', '1000004', 1590000, 8, 1],
  ['1000003', '1000013', 1710000, 11, 2],
  ['1000005', '1000019', 2130000, 10, 2],
  ['1000005', '1000013', 2390000, 13, 2],
  ['1000007', '1000008', 1880000, 6, 2],
  ['1000008', '1000010', 1450000, 7, 3],
  ['1000013', '1000014', 2200000, 12, 2],
  ['1000014', '1000015', 1730000, 9, 3],
  ['1000014', '1000017', 1400000, 8, 3],
  ['1000017', '1000018', 1660000, 10, 3],
  ['1000018', '1000019', 1570000, 6, 3],
  ['1000019', '1000020', 2580000, 13, 2],
  ['1000019', '1000001', 1480000, 4, 1],
  ['1000020', '1000011', 1475000, 7, 2],
  ['1000011', '1000012', 1360000, 6, 2],
  ['1000011', '1000015', 1640000, 9, 3],
  ['1000015', '1000016', 980000, 4, 4],
];

export const demoEdges = edgePairs.map(([src, dst, sumKzt, nTx, depth]) => ({
  src,
  dst,
  sum_kzt: sumKzt,
  n_tx: nTx,
  depth,
}));

export const demoGraph: GraphResponse = {
  nodes: demoNodes,
  edges: demoEdges,
  scope: 'full',
  total_nodes: demoNodes.length,
  total_edges: demoEdges.length,
};

const dailyFlowsFor = (gid: string, role: string): DailyFlow[] => {
  const base = Number(gid.slice(-2)) || 1;
  return Array.from({ length: 7 }, (_, i) => {
    const date = `2026-07-${String(i + 1).padStart(2, '0')}`;
    const inKzt = Number((base * 50000 + i * 12000 + (role === 'consolidator' ? 70000 : 20000)).toFixed(0));
    const outKzt = Number((base * 45000 + i * 15000 + (role === 'distributor' ? 80000 : 25000)).toFixed(0));
    return {
      date,
      in_kzt: inKzt,
      out_kzt: outKzt,
      in_tx: 2 + (i % 3),
      out_tx: 2 + ((i + 1) % 4),
    };
  });
};

export const demoNodeDetails: Record<string, NodeDetail> = Object.fromEntries(
  demoNodes.map((node) => {
    const warnings = [
      node.truncated_by_depth ? 'Узел обрезан по глубине наблюдения; исходящий поток может быть неполным.' : 'Связи видны в пределах наблюдаемого окна, метрики не равны балансу клиента.',
    ];

    if (node.is_seed) warnings.push('Seed-узел включён в сеть как контрольная точка, без полноты входящего потока.');
    if (node.pass_through === null) warnings.push('Отношение pass_through не рассчитано: недостаточно данных для оценки.');

    return [
      node.gid,
      {
        node,
        explanation: `${roleLabels[node.role]}: в расчёте учитываются входящий оборот ${node.in_kzt.toLocaleString('ru-RU')} KZT, исходящий оборот ${node.out_kzt.toLocaleString('ru-RU')} KZT и результирующий score ${node.role_score.toFixed(2)}. Порог роли поддержан фактической структурой и подвержен проверке аналитиком.`,
        warnings,
        daily_flows: dailyFlowsFor(node.gid, node.role),
      },
    ];
  }),
);

export const demoSummary = summaryData;
export const demoClusters: Cluster[] = clusterData;

export const exportCsv = (filename: string): string => {
  if (filename === 'nodes_roles.csv') {
    const header = ['gid', 'role', 'role_score', 'cluster_id', 'priority_score', 'evidence'];
    const rows = demoNodes.map((node) => [node.gid, node.role, node.role_score.toString(), node.cluster_id.toString(), node.priority_score.toString(), node.evidence]);
    return [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
  }

  if (filename === 'clusters.csv') {
    const header = ['cluster_id', 'n_nodes', 'n_seed', 'sum_kzt_internal', 'top_gids', 'hypothesis'];
    const rows = clusterData.map((cluster) => [cluster.cluster_id.toString(), cluster.n_nodes.toString(), cluster.n_seed.toString(), cluster.sum_kzt_internal.toString(), JSON.stringify(cluster.top_gids), cluster.hypothesis]);
    return [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
  }

  if (filename === 'top_nodes.csv') {
    const header = ['rank', 'gid', 'role', 'priority_score', 'why'];
    const rows = demoTopNodes.map((node) => [node.rank.toString(), node.gid, node.role, node.priority_score.toString(), node.why]);
    return [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
  }

  return '';
};

export const demoApi = {
  getSummary: async (): Promise<SummaryData> => summaryData,
  getTopNodes: async (limit: number): Promise<TopNode[]> => demoTopNodes.slice(0, limit),
  getClusters: async (): Promise<Cluster[]> => clusterData,
  getNodeByGid: async (gid: string): Promise<NodeDetail | null> => demoNodeDetails[gid] ?? null,
  getNodes: async (): Promise<NodeSummary[]> => demoNodes,
  getGraph: async (): Promise<GraphResponse> => demoGraph,
  getCsv: async (filename: string): Promise<string> => exportCsv(filename),
};
