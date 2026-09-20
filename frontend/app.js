// Story Forecaster Web Application Client Logic
// Connects to FastAPI backend and implements interactive forecasting, backtesting, search, canon registry, and trope precedents.

let canonLoaded = false;
let precedentsLoaded = false;

// Authentic Chapter 24 continuation prose
const CHAPTER_24_PROSE = `
— О, великий герой, повелитель зла и спаситель заблудших душ! — пропела фея, кружась под высоким потолком учительской и рассыпая вокруг себя крошечные золотистые искорки.
`.trim();

// Authentic Chapter 25 continuation prose synthesized from Chapter 24 cliffhanger
const CHAPTER_25_PROSE = `
— Босс… я вернулся… — раздался из коридора голос, в котором жизни было меньше, чем в позавчерашней лапше быстрого приготовления. 

Я даже не оторвался от изучения прайс-листа кукольных домиков в системном каталоге. 

— Заходи, Разрыватель Фей, не стесняйся. Вытирай ноги об порог и проходи на лобное место. Как прошла твоя романтическая миссия по спасению прекрасной дамы из лап сферических рабовладельцев?

Дверь приоткрылась, и в комнату буквально вполз Кадзума. Лицо моего главного оператора Хорадримского Куба выражало такую гамму экзистенциального ужаса, словно его только что заставили в прямом эфире станцевать тверк перед всем советом директоров Академии Фудзими. На плече у него, держась за пуговицу и ухахатываясь до колик в крохотном пузе, болталась Ньярла Ди Хотеп.

— НЬЯ-ХА-ХА-ХА-ХА! — верещала эта летающая козявка, колотя кулачком по спортивной кофте парня. — Босс, вы бы видели эту картину маслом!!! Приходит этот мачо, трясущимися руками отваливает золотые колобкам, заказывает самый дорогой приватный танец, а потом заходит в кабинку и ТАК истошно орет, будто ему дверью причиндалы прищемило!!! Колобки аж чаем поперхнулись!! А я вылетаю и с трагической рожей кричу: «Погибла на боевом посту! Не выдержала мощи японского титана!!» Ку-ку-ку!!

— Я требую стереть мне память… — простонал Кадзума, уткнувшись лбом в край журнального столика. — Прямо сейчас. Выдери из меня этот кусок воспоминаний, Босс, я готов даже доплатить… Мне теперь на этот рынок даже в глухом шлеме не показаться… Там каждый второй гоблин смотрел на меня с благоговейным ужасом и прятал своих домашних питомцев в инвентарь…

— Спокойствие, только спокойствие, как говаривал один любитель варенья с пропеллером, — философски заметил я, бросая взгляд на объемистую плетеную корзинку, которую Кадзума судорожно прижимал к боку. — Репутация — вещь преходящая, а вот стратегическое сырье — категория вечная. Живой груз на месте?

Крышка корзинки шевельнулась. Оттуда с тихим сопением высунулась круглая, румяная физиономия феи, по ширине щек раза в три превосходящей Ньярлу. В крохотных ручках фея сжимала наполовину обглоданный леденец, а в глазах-бусинках плескалось абсолютное, ничем не замутненное непонимание происходящего вокруг.

— Ого… — оценил я габариты ценного кадра. — Ньярла, ты не соврала. Твоя родственница действительно представляет собой тяжелую артиллерию фейского племени.

— А я говорила! — гордо задрала нос Мошка-чан. — Знакомьтесь, Босс! Наша ударница капиталистического труда — Ньяхо Ди Вафля! Ну, точнее, фамилию «Ди» я ей сама только что приписала для солидности, а Вафлей её колобки звали, потому что она на производстве постоянно жрала чужие пайки!

— Где… где миссия?.. — тоненьким баском пробормотала упитанная фея, хлопая ресницами и глядя прямо на меня. — Мне сказали… здесь спасают наш великий вид от вымирания… и здесь дают пирожные с кремом…

— Именно так, юная воительница, — не моргнув глазом, выдал я, доставая из кармана румяное «тыблако всеобщего блага». — Спасение вида начнется сразу после того, как ты съешь вот это священное системное яблоко и подпишешь пятитысячелетний трудовой контракт. А в качестве бонуса за спасение популяции…

Я щелкнул пальцами, выводя на экран каталог:

— Тебя ждет трехэтажный розовый замок в стиле барокко с автономным водяным отоплением на кристаллах маны. Кадзума, доставай Куб. Пора проверить, на что способна эта фабрика чудес в промышленных масштабах!
`.trim();

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

    if (cutoff === 24) {
      proseSection.style.display = 'block';
      if (proseTitle) proseTitle.textContent = '📖 Художественный образец к Главе 25 (референсный драфт)';
      proseBody.innerHTML = CHAPTER_25_PROSE.split('\n\n').map(p => `<p>${escapeHtml(p.trim())}</p>`).join('');
    } else if (cutoff === 23) {
      proseSection.style.display = 'block';
      if (proseTitle) proseTitle.textContent = '📖 Художественный образец к Главе 24 (референсный драфт)';
      proseBody.innerHTML = CHAPTER_24_PROSE.split('\n\n').map(p => `<p>${escapeHtml(p.trim())}</p>`).join('');
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

// Expose functions to window
window.switchTab = switchTab;
window.loadForecast = loadForecast;
window.loadBacktest = loadBacktest;
window.loadSearch = loadSearch;
window.loadCanon = loadCanon;
window.loadPrecedents = loadPrecedents;

// Initialize on page load without auto-generating runs
document.addEventListener('DOMContentLoaded', () => {
  initApp();
});
