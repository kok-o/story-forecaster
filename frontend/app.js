// Story Forecaster Web Application Client Logic
// Connects to FastAPI backend and implements interactive forecasting, backtesting, search, canon registry, and trope precedents.

let canonLoaded = false;
let precedentsLoaded = false;

// Switch Active Tab
function switchTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));

  const btn = document.getElementById(`tab-btn-${tabName}`);
  const content = document.getElementById(`tab-${tabName}`);
  if (btn) btn.classList.add('active');
  if (content) content.classList.add('active');

  if (tabName === 'canon' && !canonLoaded) {
    loadCanon();
  } else if (tabName === 'precedents' && !precedentsLoaded) {
    loadPrecedents();
  } else if (tabName === 'writing') {
    loadBranches();
  } else if (tabName === 'arcs') {
    loadArcs();
  } else if (tabName === 'tasks') {
    loadTasks();
  }
}


// Initial Metadata Loader
async function initApp() {
  try {
    const res = await fetch('/api/work');
    if (res.ok) {
      const data = await res.json();
      const metaEl = document.getElementById('header-work-info');
      if (metaEl) {
        metaEl.textContent = `«${data.title}» • Автор: ${data.author_name} • ${data.chapters_count} глав (${data.scenes_count} сцен)`;
      }
    }
  } catch (err) {
    console.warn('API init error:', err);
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// 1. Forecast Generator
async function loadForecast() {
  const cutoffSelect = document.getElementById('forecast-cutoff-select');
  const cutoff = parseInt(cutoffSelect.value, 10) || 23;
  const providerSelect = document.getElementById('forecast-provider-select');
  const providerName = providerSelect ? providerSelect.value : 'demo';
  const btn = document.getElementById('btn-run-forecast');
  const container = document.getElementById('forecast-candidates-container');
  const proseSection = document.getElementById('prose-reader-section');
  const proseBody = document.getElementById('prose-content-body');
  const proseTitle = document.getElementById('prose-title');

  btn.disabled = true;
  btn.innerHTML = '⚡ Формирование прогноза...';
  container.innerHTML = `<div style="color: var(--text-secondary); text-align: center; grid-column: 1/-1; padding: 3rem;">Запрос к провайдеру (${escapeHtml(providerName)})...</div>`;

  try {
    const res = await fetch('/api/forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cutoff_chapter: cutoff, num_candidates: 3, provider_name: providerName })
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Ошибка API: ${res.statusText}`);
    }

    const data = await res.json();
    renderForecastCandidates(data.candidates, data.recommended_candidate_id, container, data);

    const winningCandidate = (data.candidates || []).find(c => c.candidate_id === data.recommended_candidate_id) || (data.candidates || [])[0];
    if (winningCandidate && (winningCandidate.narrative_prose || (winningCandidate.key_events && winningCandidate.key_events.length > 0))) {
      proseSection.style.display = 'block';
      if (proseTitle) proseTitle.textContent = `📖 Сюжетный образец главы ${cutoff + 1} (${escapeHtml(winningCandidate.title || 'Рекомендованная гипотеза')})`;
      if (winningCandidate.narrative_prose) {
        proseBody.innerHTML = winningCandidate.narrative_prose.split('\n\n').map(p => `<p>${escapeHtml(p.trim())}</p>`).join('');
      } else {
        const eventsList = (winningCandidate.key_events || []).map(e => `<li><strong>Бит #${e.ordinal}:</strong> ${escapeHtml(e.summary)} <em>(${escapeHtml((e.participants || []).join(', '))})</em></li>`).join('');
        proseBody.innerHTML = `<p>${escapeHtml(winningCandidate.rationale || 'Прогнозируемая структура развития сюжета:')}</p><ul style="margin-left: 1.5rem; line-height: 1.6;">${eventsList}</ul>`;
      }
    } else {
      proseSection.style.display = 'none';
    }

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-red); text-align: center; grid-column: 1/-1; padding: 2rem;">Ошибка генерации: ${escapeHtml(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚡ Сгенерировать гипотезы главы';
  }
}

function renderForecastCandidates(candidates, recommendedId, container, forecastData) {
  if (!candidates || candidates.length === 0) {
    container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; grid-column: 1/-1;">Нет доступных кандидатов.</div>';
    return;
  }

  const isDemo = forecastData && forecastData.is_synthetic_demonstration;
  const providerLabel = isDemo ? 'ДЕМО-ШАБЛОН' : (forecastData && forecastData.provider ? forecastData.provider : 'LLM');

  container.innerHTML = candidates.map((cand, idx) => {
    const isWinner = (recommendedId && cand.candidate_id === recommendedId) || idx === 0;
    const cardClass = isWinner ? 'candidate-card primary-winner' : 'candidate-card';
    const winnerBadge = isWinner ? '<span class="badge badge-green" style="margin-bottom: 0.75rem;">🏆 ВАРИАНТ #1</span>' : '';
    const pov = cand.topology ? cand.topology.pov_character : 'Хатиман';
    const mode = cand.topology ? cand.topology.narrative_mode : 'ACTION';
    const beats = cand.key_events || [];

    const beatsHtml = beats.map(b => `
      <li class="beat-item">
        <span class="beat-num">#${b.ordinal}</span>
        <div>
          <strong style="color: var(--text-primary);">${escapeHtml(b.summary)}</strong>
          <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.25rem;">Конфликт: ${escapeHtml(b.conflict_type || 'сюжетный')}</div>
        </div>
      </li>
    `).join('');

    const verificationBadge = cand.continuity_verified 
      ? '<span class="badge badge-green">Проверено</span>' 
      : '<span class="badge badge-purple">Верификация: не проводилась</span>';

    return `
      <div class="${cardClass}">
        ${winnerBadge}
        <div class="card-header">
          <div class="card-title">${escapeHtml(cand.title || `Гипотеза #${idx + 1}`)}</div>
          <div style="display: flex; gap: 0.4rem; flex-wrap: wrap;">
            <span class="badge ${isDemo ? 'badge-yellow' : 'badge-cyan'}">${escapeHtml(providerLabel)}</span>
            ${verificationBadge}
          </div>
        </div>
        <div class="card-meta">
          <span>Топология: <strong>${escapeHtml(mode)}</strong></span>
          <span>POV: <strong>${escapeHtml(pov)}</strong></span>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Последовательность микро-битов:</div>
        <ul class="beats-list">
          ${beatsHtml}
        </ul>
        <div class="card-twist">
          ⚡ <strong>Клиффхэнгер:</strong> ${escapeHtml(cand.potential_twist || 'Не раскрывается до финала сцены')}
        </div>
        ${cand.verification_notes ? `<div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.5rem; font-style: italic;">* ${escapeHtml(cand.verification_notes)}</div>` : ''}
      </div>
    `;
  }).join('');
}

// 2. Backtest Evaluator
async function loadBacktest() {
  const cutoffSelect = document.getElementById('backtest-cutoff-select');
  const cutoff = parseInt(cutoffSelect.value, 10) || 22;
  const btn = document.getElementById('btn-run-backtest');
  const banner = document.getElementById('backtest-metrics-banner');
  const container = document.getElementById('backtest-table-container');

  btn.disabled = true;
  btn.innerHTML = '🧪 Проверка на скрытой Главе 23...';
  container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Запуск слепого прогноза и жадного двудольного сопоставления с золотым эталоном...</div>';

  try {
    const res = await fetch('/api/backtest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cutoff_chapter: cutoff })
    });

    if (!res.ok) {
      throw new Error(`Ошибка API: ${res.statusText}`);
    }

    const report = await res.json();
    banner.style.display = 'block';
    
    const bestF1 = report.best_at_1 ? report.best_at_1.event_f1 : 0;
    const recall = report.best_at_1 ? report.best_at_1.event_recall : 0;
    const prec = report.best_at_1 ? report.best_at_1.event_precision : 0;
    const oracleF1 = report.oracle_at_k ? report.oracle_at_k.event_f1 : bestF1;

    document.getElementById('metric-best-f1').textContent = `${(bestF1 * 100).toFixed(1)}%`;
    document.getElementById('metric-recall').textContent = `${(recall * 100).toFixed(1)}%`;
    document.getElementById('metric-precision').textContent = `${(prec * 100).toFixed(1)}%`;
    document.getElementById('metric-oracle-f1').textContent = `${(oracleF1 * 100).toFixed(1)}%`;

    renderBacktestTable(report, container);

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem;">Ошибка бэктеста: ${escapeHtml(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🧪 Запустить слепой бэктест';
  }
}

function renderBacktestTable(report, container) {
  const matches = (report.oracle_at_k && report.oracle_at_k.matches) ? report.oracle_at_k.matches : [];
  const testCh = report.test_chapter || 23;
  const topoScore = report.best_at_1 ? Math.round((report.best_at_1.topology_score || 0) * 100) : 0;

  const rows = matches.map((m, idx) => {
    const simPercent = Math.round(m.weight * 100);
    const statusBadge = m.weight === 1.0 
      ? '<span class="badge badge-green">Полное совпадение</span>' 
      : '<span class="badge badge-purple">Семантическое совпадение</span>';

    return `
      <tr>
        <td style="font-weight: 600; color: var(--accent-cyan);">Бит #${idx + 1}</td>
        <td>${escapeHtml(m.gold_summary)}</td>
        <td>${escapeHtml(m.predicted_summary)}</td>
        <td style="font-weight: 700; color: var(--accent-green);">${simPercent}%</td>
        <td>${statusBadge}</td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <table class="custom-table">
      <thead>
        <tr>
          <th>Бит</th>
          <th>Фактическое событие Главы ${escapeHtml(testCh)} (Gold)</th>
          <th>Слепой прогноз системы (Predicted)</th>
          <th>Вес</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
    <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 1rem; text-align: right;">
      * Топологическое совпадение структуры: <strong>${topoScore}%</strong> | Анализ отсечки для Главы ${escapeHtml(testCh)}.
    </div>
  `;
}

// 3. Hybrid Search
async function loadSearch() {
  const queryInput = document.getElementById('search-input');
  const cutoffSelect = document.getElementById('search-cutoff-select');
  const query = queryInput.value.trim();
  const cutoff = parseInt(cutoffSelect.value, 10) || 23;
  const btn = document.getElementById('btn-run-search');
  const container = document.getElementById('search-results-container');

  if (!query) return;

  btn.disabled = true;
  btn.innerHTML = '🔍 Поиск...';
  container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Поиск по индексу BM25 с RRF-слиянием и соблюдением границы cutoff...</div>';

  try {
    const res = await fetch('/api/retrieval/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query, cutoff_chapter: cutoff, top_k: 10 })
    });

    if (!res.ok) {
      throw new Error(`Ошибка API: ${res.statusText}`);
    }

    const results = await res.json();
    renderSearchResults(results, container);

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem;">Ошибка поиска: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔍 Искать';
  }
}

function renderSearchResults(results, container) {
  if (!results || results.length === 0) {
    container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">По данному запросу в пределах отсечки ничего не найдено.</div>';
    return;
  }

  const items = results.map((r, idx) => {
    return `
      <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <div>
            <strong style="color: var(--accent-cyan); font-size: 1.05rem;">Сцена #${escapeHtml(r.discourse_seq || '—')}</strong>
            <span style="color: var(--text-secondary); font-size: 0.85rem; margin-left: 0.75rem;">Глава ${escapeHtml(r.chapter_num || '—')}</span>
          </div>
          <div>
            <span class="badge badge-purple">RRF: ${Number(r.score || 0).toFixed(4)}</span>
            <span class="badge badge-cyan">Ранг #${idx + 1}</span>
          </div>
        </div>
        <div style="color: var(--text-primary); font-size: 0.95rem; line-height: 1.6; background: rgba(10, 13, 20, 0.5); padding: 0.75rem 1rem; border-radius: 6px; border-left: 3px solid var(--accent-cyan);">
          ${escapeHtml(r.content_snippet)}
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    <div style="margin-bottom: 1rem; font-size: 0.9rem; color: var(--text-secondary);">
      Найдено сцен: <strong>${results.length}</strong> (все результаты строго соответствуют discourse_seq &le; cutoff)
    </div>
    ${items}
  `;
}

// 4. Canon Registry
async function loadCanon() {
  const container = document.getElementById('canon-table-container');
  container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Загрузка реестра канона...</div>';

  try {
    const res = await fetch('/api/canon/summary?cutoff_chapter=23');
    if (!res.ok) {
      throw new Error(`Ошибка API: ${res.statusText}`);
    }

    const data = await res.json();
    canonLoaded = true;

    const statusBadges = {
      'CONFIRMED': '<span class="badge badge-green">CONFIRMED</span>',
      'MODIFIED': '<span class="badge badge-purple">MODIFIED</span>',
      'PRESUMED_INTACT': '<span class="badge badge-cyan">PRESUMED_INTACT</span>',
      'DEPENDS_ON_CHANGED_CONDITIONS': '<span class="badge badge-yellow" style="background: rgba(245, 158, 11, 0.15); color: var(--accent-yellow); border-color: rgba(245, 158, 11, 0.3);">DEPENDS_ON_CHANGED</span>',
      'UNKNOWN': '<span class="badge" style="background: rgba(100, 116, 139, 0.15); color: var(--text-muted);">UNKNOWN</span>'
    };

    const dist = data.distribution || {};
    const distHtml = Object.entries(dist).map(([k, v]) => `
      <div style="background: var(--bg-card); padding: 0.75rem 1.25rem; border-radius: 8px; border: 1px solid var(--border-color); text-align: center;">
        <div style="font-size: 0.75rem; color: var(--text-secondary);">${escapeHtml(k)}</div>
        <div style="font-size: 1.4rem; font-weight: 700; color: var(--text-primary);">${Number(v)}</div>
      </div>
    `).join('');

    const elements = data.elements || [];
    const rows = elements.map(el => `
      <tr>
        <td style="font-weight: 600; color: var(--text-primary);">${escapeHtml(el.canon_element_id || el.element_id)}</td>
        <td><span style="font-size: 0.9rem; color: var(--text-primary);">${escapeHtml(el.description)}</span></td>
        <td>${statusBadges[el.canon_relation] || escapeHtml(el.canon_relation)}</td>
        <td style="font-size: 0.85rem; color: var(--text-secondary);">${escapeHtml(el.notes || el.dependency_status || '—')}</td>
        <td style="font-size: 0.8rem; color: var(--text-muted);">HOTD Canon</td>
      </tr>
    `).join('');

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem;">
        ${distHtml}
      </div>
      <table class="custom-table">
        <thead>
          <tr>
            <th>ID Элемента</th>
            <th>Событие/Персонаж</th>
            <th>5-Статусное отношение</th>
            <th>Основания / Заметки</th>
            <th>Источник</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    `;

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem;">Ошибка загрузки канона: ${escapeHtml(err.message)}</div>`;
  }
}

// 5. Author Tropes & Precedents
async function loadPrecedents() {
  const select = document.getElementById('precedent-tag-select');
  const tag = select.value;
  const container = document.getElementById('precedents-container');

  container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Поиск по 13 книгам мета-корпуса N.B. (~20М знаков)...</div>';

  try {
    const res = await fetch(`/api/author/precedents?tags=${encodeURIComponent(tag)}`);
    if (!res.ok) {
      throw new Error(`Ошибка API: ${res.statusText}`);
    }

    const data = await res.json();
    precedentsLoaded = true;

    const transitions = data.abstracted_transitions || [];
    const transHtml = transitions.map(t => `
      <div class="precedent-card">
        <div class="precedent-title">⚡ Паттерн автора: ${escapeHtml(t.transition_id)}</div>
        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
          Источник: <span style="color: var(--accent-cyan);">${escapeHtml(t.source_work || 'Корпус N.B.')}</span>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
          Типичная ситуация: <span style="color: var(--text-primary);">${escapeHtml(t.abstract_situation)}</span>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-primary); margin-bottom: 0.5rem;">
          <strong>Характерное решение автора:</strong>
          <p style="margin-top: 0.25rem; color: var(--text-secondary);">${escapeHtml(t.author_resolution)}</p>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.75rem; font-size: 0.8rem; flex-wrap: wrap; gap: 0.5rem;">
          <span style="color: var(--accent-yellow);">Следствие: ${escapeHtml(t.consequence)}</span>
          <div style="display: flex; gap: 0.3rem; flex-wrap: wrap;">
            ${(t.applicability_tags || []).map(tg => `<span class="badge badge-purple">${escapeHtml(tg)}</span>`).join('')}
          </div>
        </div>
      </div>
    `).join('');

    const excerpts = data.corpus_excerpts || [];
    const excerptsHtml = excerpts.map(ex => `
      <div class="precedent-card" style="border-left: 4px solid var(--accent-cyan);">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
          <strong style="color: var(--accent-cyan); font-size: 0.95rem;">${escapeHtml(ex.book_title || 'Книга мета-корпуса')}</strong>
          <span class="badge badge-cyan">${escapeHtml(ex.cycle || 'Цикл N.B.')}</span>
        </div>
        <div class="precedent-excerpt">
          "${escapeHtml(ex.excerpt)}"
        </div>
        <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-muted); display: flex; gap: 0.5rem; flex-wrap: wrap;">
          ${(ex.tags || []).map(tg => `<span class="badge badge-purple">${escapeHtml(tg)}</span>`).join('')}
        </div>
      </div>
    `).join('');

    container.innerHTML = `
      <div style="margin-bottom: 1.5rem;">
        <h3 style="font-size: 1.1rem; color: var(--text-primary); margin-bottom: 1rem;">Абстрагированные паттерны мышления автора N.B.:</h3>
        ${transHtml.length ? transHtml : '<div style="color: var(--text-secondary);">Нет абстрагированных переходов для данного тега.</div>'}
      </div>
      <div>
        <h3 style="font-size: 1.1rem; color: var(--text-primary); margin-bottom: 1rem;">Цитаты-подтверждения из мета-корпуса FB2:</h3>
        ${excerptsHtml.length ? excerptsHtml : '<div style="color: var(--text-secondary);">Нет цитат для данного тега.</div>'}
      </div>
    `;

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem;">Ошибка загрузки прецедентов: ${escapeHtml(err.message)}</div>`;
  }
}

// ==========================================
// M6 / M7: Writing Workbench Client Handlers
// ==========================================

let activeBranchId = null;
let currentSelectedScene = null;
let cachedScenes = [];

async function loadBranches() {
  const select = document.getElementById('writing-branch-select');
  if (!select) return;
  try {
    const res = await fetch('/api/writing/branches');
    if (!res.ok) throw new Error('Failed to load branches');
    const branches = await res.json();
    if (branches.length === 0) {
      select.innerHTML = '<option value="">Нет созданных веток</option>';
      return;
    }
    select.innerHTML = branches.map(b => `
      <option value="${b.id}" ${b.id === activeBranchId ? 'selected' : ''}>
        ${escapeHtml(b.branch_name)} (Отсечка seq=${b.cutoff_discourse_seq}, ${b.accepted_scenes_count} сцен)
      </option>
    `).join('');
    activeBranchId = select.value;
    onBranchSelected();
  } catch (err) {
    console.error('Error loading branches:', err);
    select.innerHTML = '<option value="">Ошибка загрузки веток</option>';
  }
}

async function onBranchSelected() {
  const select = document.getElementById('writing-branch-select');
  if (!select || !select.value) return;
  activeBranchId = select.value;
  await loadBranchScenes(activeBranchId);
}

async function loadBranchScenes(branchId) {
  const container = document.getElementById('writing-scenes-list');
  if (!container) return;
  try {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">Загрузка сцен...</div>';
    const res = await fetch(`/api/writing/branches/${branchId}/scenes`);
    if (!res.ok) throw new Error('Failed to load scenes');
    cachedScenes = await res.json();

    if (cachedScenes.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">Ветка пуста. Запланируйте первую сцену справа.</div>';
      resetScenePlanner();
      return;
    }

    container.innerHTML = cachedScenes.map(sc => {
      let badgeClass = 'badge-accepted';
      if (sc.status === 'DRAFT') badgeClass = 'badge-draft';
      else if (sc.status === 'REJECTED') badgeClass = 'badge-rejected';
      else if (sc.status === 'SUPERSEDED') badgeClass = 'badge-superseded';

      return `
        <div class="scene-card-item ${currentSelectedScene && currentSelectedScene.id === sc.id ? 'active' : ''}" onclick="selectSceneById('${sc.id}')">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
            <strong style="color: var(--accent-cyan); font-size: 0.85rem;">Сцена #${sc.scene_ordinal} (v${sc.revision_num})</strong>
            <span class="badge ${badgeClass}" style="font-size: 0.65rem; padding: 0.15rem 0.4rem;">${sc.status}</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-primary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
            ${escapeHtml(sc.title)}
          </div>
        </div>
      `;
    }).join('');

    // Auto-select latest scene or maintain current selection
    if (!currentSelectedScene || !cachedScenes.some(s => s.id === currentSelectedScene.id)) {
      selectScene(cachedScenes[0]);
    } else {
      const refreshed = cachedScenes.find(s => s.id === currentSelectedScene.id);
      selectScene(refreshed);
    }

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-red); font-size: 0.85rem;">Ошибка: ${escapeHtml(err.message)}</div>`;
  }
}

function selectSceneById(sceneId) {
  const scene = cachedScenes.find(s => s.id === sceneId);
  if (scene) selectScene(scene);
}

function selectScene(scene) {
  currentSelectedScene = scene;
  document.querySelectorAll('.scene-card-item').forEach(el => el.classList.remove('active'));

  const detailEl = document.getElementById('writing-scene-detail');
  if (!detailEl) return;
  detailEl.style.display = 'block';

  document.getElementById('scene-detail-title').textContent = `Сцена #${scene.scene_ordinal}: ${scene.title}`;
  document.getElementById('scene-detail-rev-badge').textContent = `Ревизия ${scene.revision_num}`;
  
  const statusBadge = document.getElementById('scene-detail-status-badge');
  statusBadge.textContent = scene.status;
  statusBadge.className = 'badge';
  if (scene.status === 'ACCEPTED') statusBadge.classList.add('badge-accepted');
  else if (scene.status === 'DRAFT') statusBadge.classList.add('badge-draft');
  else if (scene.status === 'REJECTED') statusBadge.classList.add('badge-rejected');
  else if (scene.status === 'SUPERSEDED') statusBadge.classList.add('badge-superseded');

  // Proposed State Delta Breakdown & Provider Badge
  const delta = scene.state_delta || {};
  const providerBadge = document.getElementById('scene-detail-provider-badge');
  if (providerBadge) {
    const isSynthetic = delta.is_synthetic_demonstration;
    const provName = delta.provider_name || (isSynthetic ? 'demo' : 'llm');
    providerBadge.textContent = isSynthetic ? 'ДЕМО-ШАБЛОН' : `LLM: ${provName.toUpperCase()}`;
    providerBadge.className = 'badge ' + (isSynthetic ? 'badge-yellow' : 'badge-green');
  }

  // Prose
  document.getElementById('scene-detail-prose').innerHTML = scene.content
    .split('\n\n')
    .map(p => `<p>${escapeHtml(p)}</p>`)
    .join('');

  const deltaContainer = document.getElementById('delta-items-container');
  const deltaHtml = [];

  (delta.introduced_characters || []).forEach(c => {
    deltaHtml.push(`<span class="delta-tag delta-tag-equip">👤 Призван: ${escapeHtml(c)}</span>`);
  });

  (delta.inventory_changes || []).forEach(inv => {
    deltaHtml.push(`<span class="delta-tag delta-tag-equip">🎒 ${escapeHtml(inv.character)}: ${escapeHtml(inv.item)} (${escapeHtml(inv.action)})</span>`);
  });

  (delta.injuries_or_statuses || []).forEach(inj => {
    deltaHtml.push(`<span class="delta-tag delta-tag-status">⚠️ ${escapeHtml(inj.character)}: статус ${escapeHtml(inj.status)} (${escapeHtml(inj.action)})</span>`);
  });

  (delta.dialogue_claims || []).forEach(claim => {
    deltaHtml.push(`<span class="delta-tag delta-tag-dialogue">💬 ${escapeHtml(claim.speaker)} (диалог, факт=НЕТ): «${escapeHtml(claim.statement)}»</span>`);
  });

  deltaContainer.innerHTML = deltaHtml.length ? deltaHtml.join('') : '<span style="color: var(--text-muted); font-size: 0.85rem;">Нет активных изменений состояния.</span>';

  // Revise textarea
  document.getElementById('revise-scene-content').value = scene.content;

  // Actions visibility
  const actionsContainer = document.getElementById('scene-actions-container');
  if (actionsContainer) {
    actionsContainer.style.display = (scene.status === 'DRAFT') ? 'flex' : 'none';
  }
}

function resetScenePlanner() {
  const maxOrd = cachedScenes.reduce((max, s) => Math.max(max, s.scene_ordinal), 0);
  document.getElementById('plan-scene-ordinal').value = maxOrd + 1;
  document.getElementById('plan-scene-title').value = `Сцена #${maxOrd + 1}`;
  document.getElementById('plan-scene-beats').value = 'Действие бита 1...\nДействие бита 2...';
  document.getElementById('writing-scene-detail').style.display = 'none';
}

async function showNewBranchPrompt() {
  const name = prompt('Введите название новой альтернативной ветки:', 'Линия Кадзумы и Ярмарки');
  if (!name) return;
  const cutoff = prompt('Введите граничный sequence отсечки (напр. 182 для гл. 22):', '182');
  if (!cutoff) return;

  try {
    const res = await fetch('/api/writing/branches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        branch_name: name,
        cutoff_discourse_seq: parseInt(cutoff, 10),
        description: 'Пользовательская альтернативная сюжетная ветка'
      })
    });
    if (!res.ok) throw new Error('Не удалось создать ветку');
    const data = await res.json();
    alert(`Ветка «${data.branch_name}» успешно создана!`);
    activeBranchId = data.id;
    await loadBranches();
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

async function draftSceneFromPlan() {
  if (!activeBranchId) {
    alert('Сначала выберите или создайте ветку!');
    return;
  }

  const ordinal = parseInt(document.getElementById('plan-scene-ordinal').value, 10) || 1;
  const title = document.getElementById('plan-scene-title').value || `Сцена #${ordinal}`;
  const pov = document.getElementById('plan-scene-pov').value;
  const participants = document.getElementById('plan-scene-participants').value.split(',').map(s => s.trim()).filter(Boolean);
  const beats = document.getElementById('plan-scene-beats').value.split('\n').map(s => s.trim()).filter(Boolean);
  const initial = document.getElementById('plan-scene-initial').value;
  const outcome = document.getElementById('plan-scene-outcome').value;
  const providerName = document.getElementById('plan-scene-provider')?.value || 'demo';

  const btn = document.getElementById('btn-draft-scene');
  btn.disabled = true;
  btn.textContent = '⏳ Синтез прозы и валидация...';

  try {
    const res = await fetch(`/api/writing/branches/${activeBranchId}/draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scene_ordinal: ordinal,
        title: title,
        provider_name: providerName,
        plan: {
          scene_goal: title,
          pov_character: pov,
          participants: participants,
          initial_state_summary: initial,
          mandatory_beats: beats,
          desired_outcome: outcome,
          target_pacing: 'medium',
          target_length_chars: 2500
        }
      })
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Ошибка генерации сцены');
    }

    const data = await res.json();
    await loadBranchScenes(activeBranchId);
    selectSceneById(data.scene_id);

    // Update validation banner
    const val = data.validation || {};
    const valTitle = document.getElementById('val-banner-title');
    const valNotes = document.getElementById('val-banner-notes');
    const complianceScore = Number.isFinite(val.plan_compliance_score) ? val.plan_compliance_score : (val.passed ? 1.0 : 0.0);
    if (val.passed) {
      valTitle.textContent = `✓ Валидация пройдена: исполнение битов ${Math.round(complianceScore * 100)}%`;
      valTitle.style.color = 'var(--accent-green)';
    } else {
      valTitle.textContent = `⚠ Валидация выявила отклонения (${Math.round(complianceScore * 100)}%)`;
      valTitle.style.color = 'var(--accent-red)';
    }
    valNotes.textContent = `POV-утечки: ${(val.pov_violations || []).length} • Эпистемические нарушения: ${(val.epistemic_violations || []).length} • ${val.notes || ''}`;

  } catch (err) {
    alert(`Ошибка генерации: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Сгенерировать черновик (Draft Scene)';
  }
}

async function acceptCurrentScene() {
  if (!currentSelectedScene) return;
  try {
    const res = await fetch(`/api/writing/scenes/${currentSelectedScene.id}/accept`, { method: 'POST' });
    if (!res.ok) throw new Error('Не удалось принять сцену');
    await loadBranchScenes(activeBranchId);
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

async function rejectCurrentScene() {
  if (!currentSelectedScene) return;
  const reason = prompt('Укажите причину отклонения сцены (delta будет изолирована):', 'Несоответствие характеру');
  if (!reason) return;
  try {
    const res = await fetch(`/api/writing/scenes/${currentSelectedScene.id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason })
    });
    if (!res.ok) throw new Error('Не удалось отклонить сцену');
    await loadBranchScenes(activeBranchId);
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

async function reviseCurrentScene() {
  if (!currentSelectedScene) return;
  const newContent = document.getElementById('revise-scene-content').value;
  if (!newContent || newContent.length < 10) {
    alert('Текст ревизии слишком короткий.');
    return;
  }

  try {
    const res = await fetch(`/api/writing/scenes/${currentSelectedScene.id}/revise`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_content: newContent })
    });
    if (!res.ok) throw new Error('Не удалось создать ревизию');
    const data = await res.json();
    alert(`Ревизия #${data.revision_num} создана со статусом ${data.status}!`);
    await loadBranchScenes(activeBranchId);
    selectSceneById(data.new_scene_id);
  } catch (err) {
    alert(`Ошибка ревизии: ${err.message}`);
  }
}

async function rollbackStatusPrompt() {
  if (!activeBranchId) return;
  const charName = prompt('Имя персонажа для отмены ранения/статуса:', 'Сато Кадзума');
  if (!charName) return;
  const statusName = prompt('Название статуса/ранения (напр. panic_and_stress):', 'panic_and_stress');
  if (!statusName) return;

  try {
    const res = await fetch(`/api/writing/branches/${activeBranchId}/rollback-injury`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_id: charName, injury_status: statusName })
    });
    if (!res.ok) throw new Error('Ошибка отката');
    alert(`Статус «${statusName}» персонажа «${charName}» успешно аннулирован.`);
    await loadBranchScenes(activeBranchId);
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

async function exportBranch(format) {
  if (!activeBranchId) {
    alert('Выберите ветку для экспорта!');
    return;
  }
  try {
    const res = await fetch(`/api/writing/branches/${activeBranchId}/export?format=${format}`);
    if (!res.ok) throw new Error('Не удалось экспортировать ветку');
    const data = await res.json();
    
    // Download as file
    const blob = new Blob([data.content], { type: format === 'markdown' ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `branch_export_${activeBranchId.substring(0, 8)}.${format === 'markdown' ? 'md' : 'txt'}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert(`Ошибка экспорта: ${err.message}`);
  }
}

async function viewBranchSnapshot() {
  if (!activeBranchId) return;
  try {
    const res = await fetch(`/api/writing/branches/${activeBranchId}/snapshot`);
    if (!res.ok) throw new Error('Не удалось получить срез');
    const snap = await res.json();
    alert(`Срез памяти ветки:\nХеш: ${snap.snapshot_hash}\nАктивные персонажи: ${Object.keys(snap.active_characters || {}).join(', ')}\nЭпистемические связи: ${(snap.epistemic_states || []).length}\nГлава/Seq: ${snap.chapter_num} (seq <= ${snap.through_discourse_seq})`);
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

// ==========================================
// M7: Long Arcs & Editorial Quality Handlers
// ==========================================

let activeArcId = null;

async function loadArcs() {
  const select = document.getElementById('arcs-select');
  if (!select) return;
  try {
    const res = await fetch('/api/arcs');
    if (!res.ok) throw new Error('Failed to load arcs');
    const arcs = await res.json();
    if (arcs.length === 0) {
      select.innerHTML = '<option value="">Нет созданных арок</option>';
      return;
    }
    select.innerHTML = arcs.map(a => `<option value="${a.id}" ${a.id === activeArcId ? 'selected' : ''}>${escapeHtml(a.title)} (v${a.revision_num}, ${a.status})</option>`).join('');
    activeArcId = select.value;
    onArcSelected();
  } catch (err) {
    console.error('Error loading arcs:', err);
  }
}

async function onArcSelected() {
  const select = document.getElementById('arcs-select');
  if (!select || !select.value) return;
  activeArcId = select.value;

  try {
    const res = await fetch(`/api/arcs/${activeArcId}/commitments?current_scene=4`);
    if (!res.ok) throw new Error('Failed to load commitments');
    const data = await res.json();

    document.getElementById('metric-open-promises').textContent = data.open_commitments_count || 0;
    document.getElementById('metric-aging-promises').textContent = data.aging_commitments_count || 0;
    document.getElementById('metric-open-mysteries').textContent = data.open_mysteries_count || 0;
    document.getElementById('metric-arc-revision').textContent = `v${data.revision_num || 1}`;

    const tableContainer = document.getElementById('arc-commitments-table-container');
    const commitments = data.commitments || [];
    if (commitments.length === 0) {
      tableContainer.innerHTML = '<div style="color: var(--text-muted); padding: 1rem;">Нет зарегистрированных обязательств для данной арки.</div>';
      return;
    }

    tableContainer.innerHTML = `
      <table class="custom-table" style="margin-top: 1rem;">
        <thead>
          <tr>
            <th>Обещание (Chekhov's Gun)</th>
            <th>Сцена появления</th>
            <th>Возраст (сцен)</th>
            <th>Статус развязки</th>
            <th>Риск забывания</th>
          </tr>
        </thead>
        <tbody>
          ${commitments.map(c => `
            <tr>
              <td><strong>${escapeHtml(c.text)}</strong></td>
              <td>#${c.introduced_at}</td>
              <td>${c.current_age}</td>
              <td><span class="badge ${c.payoff_status === 'OPEN' ? 'badge-yellow' : 'badge-green'}">${c.payoff_status}</span></td>
              <td>${c.is_aging_risk ? '<span class="badge badge-red">⚠️ Высокий возраст</span>' : '<span class="badge badge-green">В норме</span>'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;

  } catch (err) {
    console.error('Error in onArcSelected:', err);
  }
}

async function showNewArcPrompt() {
  const title = prompt('Название сюжетной арки:', 'Арка Ярмарки Осколков и Автокрафта');
  if (!title) return;
  const conflict = prompt('Основной конфликт арки:', 'Шантаж феи и организация сбыта артефактов');
  if (!conflict) return;

  try {
    const res = await fetch('/api/arcs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        core_conflict: conflict,
        milestones: [
          { milestone_id: 'm1', title: 'Призыв Кадзумы', order: 1, status: 'ACHIEVED' },
          { milestone_id: 'm2', title: 'Разведка ярмарки', order: 2, status: 'IN_PROGRESS' },
          { milestone_id: 'm3', title: 'Соглашение с феей', order: 3, status: 'PENDING' }
        ],
        promises: [
          { promise_id: 'p1', introduced_in_scene_ordinal: 1, promise_text: 'Хорадримский Куб принесет миллионы золотых', payoff_status: 'OPEN' },
          { promise_id: 'p2', introduced_in_scene_ordinal: 2, promise_text: 'Фея раскроет источник дешевой пыльцы', payoff_status: 'OPEN' }
        ]
      })
    });
    if (!res.ok) throw new Error('Не удалось создать арку');
    const data = await res.json();
    alert(`Арка «${data.title}» успешно создана!`);
    activeArcId = data.id;
    await loadArcs();
  } catch (err) {
    alert(`Ошибка создания арки: ${err.message}`);
  }
}

async function runEditorialReview() {
  const container = document.getElementById('editorial-review-container');
  if (!container) return;

  // Gather scenes from cached writing workbench if available, or generate standard sample
  const sampleScenes = cachedScenes.length > 0 
    ? cachedScenes.map(s => s.content) 
    : [
        'Хачиман окинул фею холодным взглядом. — Контракт на пыльцу должен быть подписан.',
        'Кадзума побледнел как полотно: Босс, это чистый шантаж! Но отступать некуда.'
      ];

  try {
    const res = await fetch('/api/editor/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chapter_ordinal: 24,
        scenes_content: sampleScenes
      })
    });
    if (!res.ok) throw new Error('Ошибка аудита');
    const data = await res.json();
    const sc = data.scorecard || {};

    container.style.display = 'block';
    document.getElementById('score-pacing').textContent = sc.pacing_score != null ? sc.pacing_score : '-';
    document.getElementById('score-voice').textContent = sc.voice_consistency_score != null ? sc.voice_consistency_score : '-';
    document.getElementById('score-causal').textContent = sc.causal_coherence_score != null ? sc.causal_coherence_score : '-';
    document.getElementById('score-cliche').textContent = sc.repetition_penalty != null ? `-${sc.repetition_penalty}` : '-';
    document.getElementById('score-overall').textContent = sc.overall_quality_score != null ? sc.overall_quality_score : '-';

    const findingsContainer = document.getElementById('editorial-findings-container');
    const recsHtml = (data.recommendations || []).map(r => `<li>${escapeHtml(r)}</li>`).join('');
    const repHtml = (data.repetitive_phrases || []).map(p => `<span class="badge badge-yellow" style="margin: 0.2rem;">${escapeHtml(p)}</span>`).join('');
    const anomaliesHtml = (data.voice_anomalies || []).map(a => `<div style="color: var(--accent-red); font-size: 0.85rem; margin-top: 0.25rem;">⚠️ ${escapeHtml(a)}</div>`).join('');

    findingsContainer.innerHTML = `
      <div style="margin-bottom: 0.75rem;"><strong>Оценка темпа:</strong> ${escapeHtml(data.pacing_assessment || '')}</div>
      ${repHtml.length ? `<div style="margin-bottom: 0.75rem;"><strong>Обнаруженные клише/повторы:</strong><br>${repHtml}</div>` : ''}
      ${anomaliesHtml.length ? `<div style="margin-bottom: 0.75rem;"><strong>Голосовые аномалии:</strong><br>${anomaliesHtml}</div>` : ''}
      <div style="margin-top: 0.75rem;"><strong>Рекомендации редактора:</strong><ul style="margin-left: 1.5rem; margin-top: 0.25rem;">${recsHtml || '<li>Текст соответствует авторскому стандарту.</li>'}</ul></div>
    `;

  } catch (err) {
    alert(`Ошибка аудита: ${err.message}`);
  }
}

// ==========================================
// M7: Persistent Task Queue Handlers
// ==========================================

async function loadTasks() {
  const container = document.getElementById('tasks-table-container');
  if (!container) return;
  try {
    const res = await fetch('/api/tasks');
    if (!res.ok) throw new Error('Failed to load tasks');
    const tasks = await res.json();
    if (tasks.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); padding: 1.5rem; text-align: center;">Очередь задач пуста. Добавьте задачу выше.</div>';
      return;
    }

    container.innerHTML = `
      <table class="custom-table">
        <thead>
          <tr>
            <th>ID / Тип</th>
            <th>Статус</th>
            <th>Прогресс</th>
            <th>Расход ($)</th>
            <th>Создана</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          ${tasks.map(t => {
            let statusBadge = 'badge-cyan';
            if (t.status === 'COMPLETED') statusBadge = 'badge-green';
            else if (t.status === 'RUNNING') statusBadge = 'badge-yellow';
            else if (t.status === 'CANCELLED') statusBadge = 'badge-purple';
            else if (t.status === 'FAILED') statusBadge = 'badge-red';

            return `
              <tr>
                <td>
                  <strong>${escapeHtml(t.task_type)}</strong>
                  <div style="font-size: 0.75rem; color: var(--text-muted); font-family: monospace;">${t.id.substring(0, 8)}...</div>
                </td>
                <td><span class="badge ${statusBadge}">${t.status}</span></td>
                <td style="min-width: 150px;">
                  <div style="font-size: 0.8rem; font-weight: 600;">${t.progress_pct}%</div>
                  <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${t.progress_pct}%;"></div></div>
                </td>
                <td>$${Number(t.cost_usd || 0).toFixed(4)}</td>
                <td style="font-size: 0.8rem; color: var(--text-secondary);">${t.created_at ? t.created_at.substring(11, 19) : '-'}</td>
                <td>
                  <div style="display: flex; gap: 0.4rem;">
                    ${t.status === 'QUEUED' || t.status === 'RUNNING' ? `
                      <button class="btn-primary" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="runTaskWorker('${t.id}')">Запустить шаг</button>
                      <button class="btn-danger" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="cancelTask('${t.id}')">Отмена</button>
                    ` : '<span style="color: var(--text-muted); font-size: 0.8rem;">Завершена</span>'}
                  </div>
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-red); padding: 1rem;">Ошибка загрузки задач: ${escapeHtml(err.message)}</div>`;
  }
}

async function enqueueTask() {
  const type = document.getElementById('task-type-select').value;
  const steps = parseInt(document.getElementById('task-steps-input').value, 10) || 4;
  const budget = parseFloat(document.getElementById('task-budget-input').value) || 0.50;

  try {
    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_type: type,
        params: { steps: steps, unit_cost_usd: 0.015 },
        max_cost_limit_usd: budget
      })
    });
    if (!res.ok) throw new Error('Не удалось поставить задачу в очередь');
    await loadTasks();
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

async function runTaskWorker(taskId) {
  try {
    const res = await fetch(`/api/tasks/${taskId}/run`, { method: 'POST' });
    if (!res.ok) throw new Error('Ошибка запуска задачи');
    await loadTasks();
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

async function cancelTask(taskId) {
  try {
    const res = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error('Не удалось отменить задачу');
    await loadTasks();
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  }
}

// Expose functions to window
window.switchTab = switchTab;
window.loadForecast = loadForecast;
window.loadBacktest = loadBacktest;
window.loadSearch = loadSearch;
window.loadCanon = loadCanon;
window.loadPrecedents = loadPrecedents;

// Writing Workbench exposed
window.loadBranches = loadBranches;
window.onBranchSelected = onBranchSelected;
window.showNewBranchPrompt = showNewBranchPrompt;
window.draftSceneFromPlan = draftSceneFromPlan;
window.selectSceneById = selectSceneById;
window.acceptCurrentScene = acceptCurrentScene;
window.rejectCurrentScene = rejectCurrentScene;
window.reviseCurrentScene = reviseCurrentScene;
window.rollbackStatusPrompt = rollbackStatusPrompt;
window.exportBranch = exportBranch;
window.viewBranchSnapshot = viewBranchSnapshot;
window.resetScenePlanner = resetScenePlanner;

// Arcs & Editorial exposed
window.loadArcs = loadArcs;
window.onArcSelected = onArcSelected;
window.showNewArcPrompt = showNewArcPrompt;
window.runEditorialReview = runEditorialReview;

// Tasks exposed
window.loadTasks = loadTasks;
window.enqueueTask = enqueueTask;
window.runTaskWorker = runTaskWorker;
window.cancelTask = cancelTask;

// Initialize on page load without auto-generating runs
document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

