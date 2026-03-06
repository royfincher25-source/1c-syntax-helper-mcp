/**
 * Load Testing сценарий для 1C Syntax Helper MCP Server
 * 
 * Запуск:
 *   k6 run --duration 5m --vus 10 tests/load/k6_load_test.js
 * 
 * Стресс тест:
 *   k6 run --duration 2m --vus 50 tests/load/k6_load_test.js
 * 
 * Soak тест (30 мин):
 *   k6 run --duration 30m --vus 20 tests/load/k6_load_test.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// =============================================================================
// Кастомные метрики
// =============================================================================

// Error rate
const errorRate = new Rate('errors');

// Время ответа для разных endpoints
const searchDuration = new Trend('search_duration');
const healthDuration = new Trend('health_duration');
const mcpDuration = new Trend('mcp_duration');

// Счётчики запросов
const searchRequests = new Counter('search_requests');
const healthRequests = new Counter('health_requests');
const mcpRequests = new Counter('mcp_requests');

// =============================================================================
// Конфигурация
// =============================================================================

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Тестовые данные
const SEARCH_QUERIES = [
    'СтрДлина',
    'СтрЗаменить',
    'ЧислоПрописью',
    'ТаблицаЗначений',
    'ТаблицаЗначений.Добавить',
    'Массив.Добавить',
    'Структура',
    'СообщениеПользователю',
    'Формат',
    'Попытка'
];

const MCP_REQUESTS = [
    {
        tool: 'search_1c_syntax',
        arguments: { query: 'СтрДлина' }
    },
    {
        tool: 'search_1c_syntax',
        arguments: { query: 'ТаблицаЗначений.Добавить' }
    },
    {
        tool: 'get_1c_function_details',
        arguments: { element_name: 'ЧислоПрописью' }
    }
];

// =============================================================================
// Настройки сценария
// =============================================================================

export const options = {
    // Этапы нагрузочного теста
    stages: [
        { duration: '1m', target: 5 },   // Разогрев: 5 пользователей
        { duration: '2m', target: 20 },  // Нагрузка: 20 пользователей
        { duration: '5m', target: 20 },  // Пик: 20 пользователей
        { duration: '2m', target: 0 },   // Остывание
    ],
    
    // Пороговые значения (thresholds)
    thresholds: {
        http_req_duration: ['p(95)<500'], // 95% запросов < 500ms
        search_duration: ['p(95)<300'],   // 95% поисков < 300ms
        health_duration: ['p(95)<100'],   // 95% health checks < 100ms
        errors: ['rate<0.1'],             // < 10% ошибок
        http_req_failed: ['rate<0.05']    // < 5% HTTP ошибок
    },
    
    // Дополнительные настройки
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
    noConnectionReuse: false,
    userAgent: 'k6-load-test/1.0',
};

// =============================================================================
// Функции
// =============================================================================

// Выбор случайного запроса из списка
function getRandomQuery() {
    return SEARCH_QUERIES[Math.floor(Math.random() * SEARCH_QUERIES.length)];
}

// Выбор случайного MCP запроса
function getRandomMCPRequest() {
    return MCP_REQUESTS[Math.floor(Math.random() * MCP_REQUESTS.length)];
}

// =============================================================================
// Сценарии
// =============================================================================

// Поиск по синтаксису 1С
function searchSyntax() {
    const query = getRandomQuery();
    const url = `${BASE_URL}/mcp`;
    
    const payload = {
        tool: 'search_1c_syntax',
        arguments: { query: query }
    };
    
    const params = {
        headers: { 'Content-Type': 'application/json' },
        timeout: '5s'
    };
    
    searchRequests.add(1);
    
    const response = http.post(url, JSON.stringify(payload), params);
    
    const success = check(response, {
        'search: status is 200': (r) => r.status === 200,
        'search: has content': (r) => r.json().content !== undefined,
        'search: duration < 500ms': (r) => r.timings.duration < 500,
    });
    
    errorRate.add(!success);
    searchDuration.add(response.timings.duration);
    
    sleep(0.5); // Пауза между запросами
}

// Health check
function checkHealth() {
    const url = `${BASE_URL}/health`;
    
    healthRequests.add(1);
    
    const response = http.get(url, { timeout: '2s' });
    
    const success = check(response, {
        'health: status is 200': (r) => r.status === 200,
        'health: status is healthy': (r) => r.json().status === 'healthy',
        'health: duration < 100ms': (r) => r.timings.duration < 100,
    });
    
    errorRate.add(!success);
    healthDuration.add(response.timings.duration);
    
    sleep(2); // Health check реже
}

// MCP запрос
function mcpRequest() {
    const payload = getRandomMCPRequest();
    const url = `${BASE_URL}/mcp`;
    
    const params = {
        headers: { 'Content-Type': 'application/json' },
        timeout: '5s'
    };
    
    mcpRequests.add(1);
    
    const response = http.post(url, JSON.stringify(payload), params);
    
    const success = check(response, {
        'mcp: status is 200': (r) => r.status === 200,
        'mcp: has content': (r) => r.json().content !== undefined,
        'mcp: duration < 500ms': (r) => r.timings.duration < 500,
    });
    
    errorRate.add(!success);
    mcpDuration.add(response.timings.duration);
    
    sleep(1);
}

// Детальный health check
function checkHealthDetailed() {
    const url = `${BASE_URL}/health/detailed`;
    
    healthRequests.add(1);
    
    const response = http.get(url, { timeout: '3s' });
    
    const success = check(response, {
        'health detailed: status is 200': (r) => r.status === 200,
        'health detailed: has checks': (r) => r.json().checks !== undefined,
        'health detailed: duration < 200ms': (r) => r.timings.duration < 200,
    });
    
    errorRate.add(!success);
    healthDuration.add(response.timings.duration);
    
    sleep(3);
}

// =============================================================================
// Основной сценарий
// =============================================================================

export default function () {
    // Распределение нагрузки:
    // 60% - поиск
    // 20% - MCP запросы
    // 15% - health check
    // 5%  - detailed health
    
    const rand = Math.random();
    
    if (rand < 0.60) {
        searchSyntax();
    } else if (rand < 0.80) {
        mcpRequest();
    } else if (rand < 0.95) {
        checkHealth();
    } else {
        checkHealthDetailed();
    }
}

// =============================================================================
// Вывод результатов
// =============================================================================

export function handleSummary(data) {
    // Формируем отчёт
    const report = {
        timestamp: new Date().toISOString(),
        test_type: 'load_test',
        summary: {
            total_requests: data.metrics.http_reqs.values.count,
            avg_duration: data.metrics.http_req_duration.values.avg.toFixed(2) + 'ms',
            p95_duration: data.metrics.http_req_duration.values['p(95)'].toFixed(2) + 'ms',
            p99_duration: data.metrics.http_req_duration.values['p(99)'].toFixed(2) + 'ms',
            error_rate: (data.metrics.errors.values.rate * 100).toFixed(2) + '%',
            search_p95: data.metrics.search_duration.values['p(95)'].toFixed(2) + 'ms',
            health_p95: data.metrics.health_duration.values['p(95)'].toFixed(2) + 'ms',
        },
        thresholds: {
            http_req_duration_p95: data.metrics.http_req_duration.values['p(95)'] < 500 ? '✅' : '❌',
            search_duration_p95: data.metrics.search_duration.values['p(95)'] < 300 ? '✅' : '❌',
            health_duration_p95: data.metrics.health_duration.values['p(95)'] < 100 ? '✅' : '❌',
            error_rate: data.metrics.errors.values.rate < 0.1 ? '✅' : '❌',
        }
    };
    
    // Вывод в консоль
    console.log('\n=== LOAD TEST REPORT ===');
    console.log(JSON.stringify(report, null, 2));
    console.log('========================\n');
    
    // Возвращаем стандартный вывод k6
    return {
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
    };
}

function textSummary(data, options) {
    // Простая текстовая сводка
    return `
EXECUTION SUMMARY:
  total requests: ${data.metrics.http_reqs.values.count}
  avg duration: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms
  p(95) duration: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms
  p(99) duration: ${data.metrics.http_req_duration.values['p(99)'].toFixed(2)}ms
  error rate: ${(data.metrics.errors.values.rate * 100).toFixed(2)}%
`;
}
