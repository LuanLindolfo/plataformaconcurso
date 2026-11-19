import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import json
import os

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# ==============================================================================
st.set_page_config(
    page_title="Gerador de Simulados IA — Padrão Banca",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Remove margens excessivas do Streamlit para a plataforma HTML ocupar a tela toda
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
        }
        header[data-testid="stHeader"] {
            background: transparent;
        }
    </style>
""", unsafe_allow_html=True)


# ==============================================================================
# SCHEMAS PYDANTIC (GARANTEM O FORMATO EXATO QUE O SEU JAVASCRIPT ESPERA)
# ==============================================================================
class Alternativas(BaseModel):
    A: str
    B: str
    C: str
    D: str
    E: str


class QuestaoSchema(BaseModel):
    id: int
    disciplina: str
    topico: str
    hasBaseText: bool = Field(description="True se a questão depender do texto-base de Língua Portuguesa")
    enunciado: str
    alternativas: Alternativas
    correta: str = Field(description="Letra da alternativa correta: A, B, C, D ou E")
    justificativaCorreta: str
    analiseErros: Alternativas = Field(description="Explicação detalhada do porquê cada alternativa A, B, C, D e E está certa ou errada")


class TextoBaseSchema(BaseModel):
    titulo: str
    autor: str
    paragrafos: list[str]


class DisciplinaMetaSchema(BaseModel):
    name: str
    shortName: str
    tieOrder: str = Field(description="Ex: 1º Critério, 2º Critério...")
    questionsCount: int
    maxPoints: float


class SimuladoCompletoSchema(BaseModel):
    titulo_simulado: str
    subtitulo_cargo: str
    badge_edital: str
    sigla_instituicao: str
    nota_minima_pct: float = Field(default=0.6, description="Percentual mínimo para aprovação, ex: 0.6 para 60%")
    tempo_minutos: int = Field(default=180, description="Tempo total sugerido para a prova em minutos")
    texto_base: TextoBaseSchema
    disciplinas_meta: list[DisciplinaMetaSchema]
    questoes: list[QuestaoSchema]


# ==============================================================================
# FUNÇÃO DE PESQUISA NA WEB + GERAÇÃO DO SIMULADO VIA GEMINI
# ==============================================================================
def gerar_simulado_com_ia(
    api_key: str,
    concurso_orgao: str,
    banca: str,
    cargo_edital: str,
    assuntos_pedido: str,
    qtd_questoes: int,
    nivel_dificuldade: str
) -> dict:
    client = genai.Client(api_key=api_key)

    prompt = f"""
    Você é um especialista sênior em elaboração de provas de concursos públicos brasileiros.

    TAREFA OBRIGATÓRIA DE PESQUISA (USE O GOOGLE SEARCH):
    1. Pesquise informações reais e atualizadas sobre o concurso/órgão: "{concurso_orgao}", cargo/edital: "{cargo_edital}" e a banca organizadora: "{banca}".
    2. Investigue o estilo de cobrança da banca {banca} (tamanho e estrutura dos enunciados, nível de literalidade da lei vs. casos práticos, pegadinhas recorrentes, número de alternativas — mantenha sempre 5 alternativas de A a E — e critérios de desempate por disciplina se houver).
    3. Pesquise o conteúdo programático e a legislação atualizada referentes aos assuntos solicitados pelo usuário:
       "{assuntos_pedido}"

    ELABORAÇÃO DO SIMULADO:
    - Gere exatamente {qtd_questoes} questões inéditas, rigorosamente no padrão da banca {banca} e fiéis aos assuntos pedidos.
    - Numere os IDs das questões sequencialmente de 1 até {qtd_questoes}.
    - Se houver questões de Língua Portuguesa que exijam interpretação/gramática textual, crie um texto-base coerente em `texto_base` (3 a 4 parágrafos) e marque `hasBaseText: true` nas questões vinculadas a ele (começando pela questão 1). Caso não haja Língua Portuguesa, preencha `texto_base` com um texto curto institucional e marque `hasBaseText: false` em todas.
    - Em `disciplinas_meta`, liste todas as disciplinas presentes nas questões geradas, ordenadas por prioridade/critério de desempate, informando a quantidade exata de questões (`questionsCount`) e pontuação máxima (`maxPoints` considerando 0.2 ponto por questão, ou proporcional).
    - Em `analiseErros`, justifique individualmente cada uma das 5 letras (A, B, C, D e E), apontando o erro exato nos distratores e confirmando a correta, no estilo técnico de gabarito comentado.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],  # Pesquisa ativa na web para edital, banca e leis
            response_mime_type="application/json",
            response_schema=SimuladoCompletoSchema,
            temperature=0.35,
        ),
    )

    return json.loads(response.text)


# ==============================================================================
# TEMPLATE HTML/JS BASE (SUA PLATAFORMA ADAPTADA PARA RECEBER DADOS DINÂMICOS)
# ==============================================================================
def renderizar_plataforma_html(dados_simulado: dict) -> str:
    # Serializa os dados gerados pela IA para injeção segura no JavaScript
    json_texto_base = json.dumps(dados_simulado["texto_base"], ensure_ascii=False)
    json_questoes = json.dumps(dados_simulado["questoes"], ensure_ascii=False)
    json_disciplinas = json.dumps(dados_simulado["disciplinas_meta"], ensure_ascii=False)

    titulo = dados_simulado.get("titulo_simulado", "Simulado Personalizado IA")
    subtitulo = dados_simulado.get("subtitulo_cargo", "Simulado Direcionado")
    badge = dados_simulado.get("badge_edital", "Padrão Banca")
    sigla = dados_simulado.get("sigla_instituicao", "SIM")[:6].upper()
    total_q = len(dados_simulado["questoes"])
    tempo_segundos = dados_simulado.get("tempo_minutos", 180) * 60
    nota_minima_pct = dados_simulado.get("nota_minima_pct", 0.6)
    storage_suffix = str(abs(hash(titulo + subtitulo)))[:8]

    # Gera as opções do select de modo e os botões de filtro de disciplina dinamicamente
    options_disciplinas_html = f'<option value="ALL" class="bg-navy-900 text-white">Simulado Completo ({total_q} Q)</option>\n'
    pills_disciplinas_html = f'''
      <button onclick="setDisciplineViewFilter('ALL')" data-disc="ALL" class="disc-pill px-3 py-1.5 rounded-xl text-xs font-bold bg-navy-800 text-white transition cursor-pointer">
        Todas ({total_q})
      </button>
    '''
    select_res_disc_html = '<option value="ALL">Todas as Disciplinas</option>\n'

    for d in dados_simulado["disciplinas_meta"]:
        d_name = d["name"]
        d_short = d["shortName"]
        d_cnt = d["questionsCount"]
        options_disciplinas_html += f'<option value="{d_name}" class="bg-navy-900 text-white">Treino: {d_short} ({d_cnt} Q)</option>\n'
        pills_disciplinas_html += f'''
          <button onclick="setDisciplineViewFilter('{d_name}')" data-disc="{d_name}" class="disc-pill px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition cursor-pointer">
            {d_short} ({d_cnt})
          </button>
        '''
        select_res_disc_html += f'<option value="{d_name}">{d_short}</option>\n'

    html_code = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{titulo}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          fontFamily: {{ sans: ['Inter', 'sans-serif'] }},
          colors: {{
            navy: {{
              50: '#f0f4f8', 100: '#d9e2ec', 200: '#bcccdc', 300: '#9fb3c8',
              400: '#829ab1', 500: '#627d98', 600: '#486581', 700: '#334e68',
              800: '#243b53', 900: '#102a43',
            }}
          }}
        }}
      }}
    }};
  </script>
  <style>
    html {{ scroll-behavior: smooth; }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: #f1f5f9; }}
    ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 9999px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}
  </style>
</head>
<body class="bg-slate-100 text-slate-800 font-sans antialiased min-h-screen flex flex-col">

  <div id="toast-container" class="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none"></div>

  <div id="custom-modal" class="fixed inset-0 z-50 hidden items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
    <div class="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 border border-slate-200">
      <div class="flex items-start gap-3">
        <div id="modal-icon" class="w-10 h-10 rounded-xl bg-navy-100 text-navy-800 flex items-center justify-center shrink-0 font-bold text-lg">!</div>
        <div class="flex-1">
          <h3 id="modal-title" class="text-lg font-bold text-slate-900">Confirmação</h3>
          <p id="modal-message" class="text-sm text-slate-600 mt-1 leading-relaxed"></p>
        </div>
      </div>
      <div id="modal-actions" class="mt-6 flex items-center justify-end gap-3">
        <button id="modal-cancel-btn" class="px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-100 transition cursor-pointer">Cancelar</button>
        <button id="modal-confirm-btn" class="px-5 py-2.5 rounded-xl text-sm font-semibold bg-navy-800 text-white hover:bg-navy-900 shadow-sm transition cursor-pointer">Confirmar</button>
      </div>
    </div>
  </div>

  <header class="bg-navy-900 text-white shadow-lg sticky top-0 z-40 border-b border-navy-800">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-3">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center font-extrabold text-white shadow-inner shrink-0 text-xs tracking-tight">
            {sigla}
          </div>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-base sm:text-lg font-extrabold tracking-tight text-white">{titulo}</h1>
              <span class="px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30">
                {badge}
              </span>
            </div>
            <p class="text-xs text-navy-200 mt-0.5">{subtitulo} • {total_q} Questões</p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2 sm:gap-3">
          <div class="flex items-center bg-navy-800/90 border border-navy-700 rounded-xl p-1">
            <select id="exam-mode-select" onchange="handleModeChange()" class="bg-transparent text-xs sm:text-sm font-semibold text-white px-2.5 py-1.5 rounded-lg focus:outline-none cursor-pointer">
              {options_disciplinas_html}
            </select>
          </div>

          <div id="timer-box" class="flex items-center gap-2 bg-navy-800 border border-navy-700 px-3 py-1.5 rounded-xl">
            <span id="timer-display" class="font-mono text-sm sm:text-base font-bold text-white tracking-wider">03:00:00</span>
            <button id="timer-toggle-btn" onclick="toggleTimer()" class="ml-1 px-2 py-0.5 rounded-lg bg-navy-700 hover:bg-navy-600 text-xs font-semibold text-navy-100 transition cursor-pointer">Pausar</button>
          </div>

          <button onclick="confirmResetExam()" class="px-3 py-2 rounded-xl bg-navy-800 hover:bg-navy-700 border border-navy-700 text-xs font-semibold text-navy-100 transition cursor-pointer">Reiniciar</button>
        </div>
      </div>

      <nav class="flex items-center gap-2 mt-3 pt-2.5 border-t border-navy-800/80 overflow-x-auto">
        <button id="tab-btn-prova" onclick="switchTab('prova')" class="tab-btn flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition whitespace-nowrap cursor-pointer bg-white text-navy-900 shadow-xs">
          <span>📝 Prova / Simulado</span>
          <span id="nav-progress-badge" class="px-2 py-0.5 rounded-full text-[11px] bg-navy-100 text-navy-800">0/{total_q}</span>
        </button>

        <button id="tab-btn-resultado" onclick="switchTab('resultado')" class="tab-btn flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition whitespace-nowrap cursor-pointer text-navy-200 hover:bg-navy-800 hover:text-white">
          <span>📊 Resultado & Gabarito Comentado</span>
          <span id="nav-score-badge" class="hidden px-2 py-0.5 rounded-full text-[11px] bg-emerald-500 text-white font-extrabold">0,0 pts</span>
        </button>

        <button id="tab-btn-caderno" onclick="switchTab('caderno')" class="tab-btn flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition whitespace-nowrap cursor-pointer text-navy-200 hover:bg-navy-800 hover:text-white">
          <span>📓 Caderno de Erros</span>
          <span id="nav-errors-badge" class="px-2 py-0.5 rounded-full text-[11px] bg-rose-500 text-white font-extrabold">0</span>
        </button>
      </nav>
    </div>
  </header>

  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
    <!-- TAB 1: PROVA -->
    <section id="view-prova" class="block">
      <div class="bg-white rounded-2xl shadow-xs border border-slate-200 p-4 sm:p-5 mb-6">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <h2 class="text-sm sm:text-base font-bold text-slate-900 flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
              Instruções da Prova Objetiva
            </h2>
            <p class="text-xs text-slate-600 mt-1">
              Cada questão vale <strong>0,2 ponto</strong>. Clique no ícone <span class="inline-flex items-center px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[11px]">✂️</span> ao lado de cada alternativa para riscar distratores.
            </p>
          </div>
          <button onclick="scrollToFirstUnanswered()" class="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition cursor-pointer shrink-0">
            Ir para 1ª em branco
          </button>
        </div>

        <div id="discipline-filter-bar" class="flex flex-wrap items-center gap-2 pt-3">
          {pills_disciplinas_html}
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div id="questions-container" class="lg:col-span-8 space-y-5"></div>

        <aside class="lg:col-span-4 lg:sticky lg:top-28 space-y-4">
          <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4 sm:p-5">
            <div class="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 class="text-sm font-extrabold text-navy-900 uppercase tracking-wide">Cartão-Resposta Digital</h3>
                <p class="text-[11px] text-slate-500 mt-0.5">Clique no número para navegar</p>
              </div>
              <span id="sidebar-completion-pct" class="px-2.5 py-1 rounded-lg bg-navy-50 text-navy-800 text-xs font-extrabold">0%</span>
            </div>

            <div class="grid grid-cols-3 gap-2 my-3 text-center">
              <div class="bg-navy-50/70 rounded-xl p-2 border border-navy-100">
                <div id="stat-answered" class="text-base font-extrabold text-navy-900">0</div>
                <div class="text-[11px] font-medium text-navy-600">Marcadas</div>
              </div>
              <div class="bg-slate-50 rounded-xl p-2 border border-slate-200">
                <div id="stat-unanswered" class="text-base font-extrabold text-slate-700">{total_q}</div>
                <div class="text-[11px] font-medium text-slate-500">Em Branco</div>
              </div>
              <div class="bg-amber-50 rounded-xl p-2 border border-amber-200">
                <div id="stat-flagged" class="text-base font-extrabold text-amber-700">0</div>
                <div class="text-[11px] font-medium text-amber-700">Dúvida</div>
              </div>
            </div>

            <div id="answer-grid" class="grid grid-cols-5 gap-1.5 max-h-[340px] overflow-y-auto pr-1"></div>

            <div class="mt-4 pt-4 border-t border-slate-100">
              <button onclick="openFinishModal()" class="w-full py-3.5 px-4 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 hover:from-emerald-700 hover:to-teal-800 text-white font-extrabold text-sm shadow-md hover:shadow-lg transition flex items-center justify-center gap-2 cursor-pointer">
                <span>Finalizar e Corrigir Simulado</span>
              </button>
            </div>
          </div>
        </aside>
      </div>
    </section>

    <!-- TAB 2: RESULTADO -->
    <section id="view-resultado" class="hidden space-y-6">
      <div id="resultado-empty-state" class="bg-white rounded-2xl shadow-xs border border-slate-200 p-10 text-center max-w-xl mx-auto">
        <div class="w-16 h-16 rounded-2xl bg-navy-50 text-navy-800 flex items-center justify-center mx-auto text-2xl font-bold mb-4">📊</div>
        <h2 class="text-xl font-extrabold text-slate-900">Simulado ainda não finalizado</h2>
        <p class="text-sm text-slate-600 mt-2">Responda às questões e clique em <strong>Finalizar e Corrigir Simulado</strong>.</p>
        <button onclick="switchTab('prova')" class="mt-6 px-6 py-3 rounded-xl bg-navy-800 hover:bg-navy-900 text-white font-bold text-sm transition cursor-pointer">Voltar para a Prova</button>
      </div>

      <div id="resultado-content" class="hidden space-y-6">
        <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <div class="bg-navy-900 text-white p-6 sm:p-8">
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
              <div>
                <span class="text-xs font-bold uppercase tracking-wider text-navy-300">Boletim de Desempenho</span>
                <div class="flex items-baseline gap-4 mt-2">
                  <div id="res-final-score" class="text-4xl sm:text-5xl font-black text-white">0,0</div>
                  <div class="text-sm text-navy-200">de <strong class="text-white" id="res-max-score">10,0</strong> pontos possíveis</div>
                </div>
                <div id="res-status-badge" class="mt-3 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs sm:text-sm font-extrabold"></div>
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div class="bg-navy-800/90 border border-navy-700 rounded-xl p-3.5 text-center">
                  <div id="res-total-hits" class="text-2xl font-extrabold text-emerald-400">0</div>
                  <div class="text-xs text-navy-200 mt-0.5">Acertos</div>
                </div>
                <div class="bg-navy-800/90 border border-navy-700 rounded-xl p-3.5 text-center">
                  <div id="res-total-errors" class="text-2xl font-extrabold text-rose-400">0</div>
                  <div class="text-xs text-navy-200 mt-0.5">Erros</div>
                </div>
                <div class="bg-navy-800/90 border border-navy-700 rounded-xl p-3.5 text-center">
                  <div id="res-total-blank" class="text-2xl font-extrabold text-slate-300">0</div>
                  <div class="text-xs text-navy-200 mt-0.5">Em Branco</div>
                </div>
                <div class="bg-navy-800/90 border border-navy-700 rounded-xl p-3.5 text-center">
                  <div id="res-time-spent" class="text-lg sm:text-xl font-extrabold text-amber-300 font-mono mt-0.5">00:00</div>
                  <div class="text-xs text-navy-200 mt-1">Tempo Gasto</div>
                </div>
              </div>
            </div>
          </div>

          <div class="bg-emerald-50 border-t border-emerald-200 px-6 py-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-2.5 text-xs sm:text-sm text-emerald-900">
              <span class="text-lg">📓</span>
              <span id="res-notebook-sync-msg"><strong>Caderno de Erros atualizado!</strong></span>
            </div>
            <button onclick="switchTab('caderno')" class="px-4 py-2 rounded-xl bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold transition shrink-0 cursor-pointer">Abrir Caderno de Erros →</button>
          </div>
        </div>

        <div class="bg-white rounded-2xl shadow-xs border border-slate-200 p-5 sm:p-6">
          <h3 class="text-base font-extrabold text-slate-900 mb-4">Desempenho por Disciplina</h3>
          <div class="overflow-x-auto">
            <table class="w-full text-left border-collapse">
              <thead>
                <tr class="border-b border-slate-200 text-[11px] font-bold uppercase tracking-wider text-slate-500 bg-slate-50">
                  <th class="py-3 px-3 rounded-tl-xl">Prioridade</th>
                  <th class="py-3 px-3">Disciplina</th>
                  <th class="py-3 px-3 text-center">Questões</th>
                  <th class="py-3 px-3 text-center">Acertos</th>
                  <th class="py-3 px-3 text-center">Erros</th>
                  <th class="py-3 px-3 text-center">Aproveitamento</th>
                  <th class="py-3 px-3 text-right rounded-tr-xl">Pontuação</th>
                </tr>
              </thead>
              <tbody id="res-discipline-table-body" class="divide-y divide-slate-100 text-sm"></tbody>
            </table>
          </div>
        </div>

        <div class="bg-white rounded-2xl shadow-xs border border-slate-200 p-5 sm:p-6">
          <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 pb-4 border-b border-slate-100">
            <div>
              <h3 class="text-base sm:text-lg font-extrabold text-slate-900">Gabarito Oficial Comentado</h3>
              <p class="text-xs text-slate-500 mt-0.5">Revise cada questão ou clique em <strong>+ Caderno</strong> se acertou no chute.</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <button onclick="setResultFilter('ALL')" data-rfilter="ALL" class="rfilter-btn px-3 py-1.5 rounded-xl text-xs font-bold bg-navy-800 text-white cursor-pointer">Todas</button>
              <button onclick="setResultFilter('WRONG')" data-rfilter="WRONG" class="rfilter-btn px-3 py-1.5 rounded-xl text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200 cursor-pointer">❌ Erros</button>
              <button onclick="setResultFilter('CORRECT')" data-rfilter="CORRECT" class="rfilter-btn px-3 py-1.5 rounded-xl text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 cursor-pointer">✅ Acertos</button>
              <select id="res-discipline-filter" onchange="renderCommentedKey()" class="px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200 cursor-pointer">
                {select_res_disc_html}
              </select>
            </div>
          </div>
          <div id="commented-key-list" class="mt-5 space-y-6"></div>
        </div>
      </div>
    </section>

    <!-- TAB 3: CADERNO DE ERROS -->
    <section id="view-caderno" class="hidden space-y-6">
      <div class="bg-white rounded-2xl shadow-xs border border-slate-200 p-5 sm:p-6">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h2 class="text-lg sm:text-xl font-extrabold text-slate-900">📓 Caderno de Erros Inteligente</h2>
            <p class="text-xs sm:text-sm text-slate-600 mt-1">Anote sua <strong>Regra de Ouro</strong> e exporte em Markdown para gerar novos treinos focados nas suas falhas.</p>
          </div>
          <div class="flex flex-wrap items-center gap-2.5 shrink-0">
            <button onclick="copyNotebookMarkdown()" class="px-4 py-2.5 rounded-xl bg-navy-800 hover:bg-navy-900 text-white text-xs font-bold cursor-pointer">📋 Copiar Markdown</button>
            <button onclick="downloadNotebookMarkdown()" class="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold cursor-pointer">⬇️ Baixar .MD</button>
            <button onclick="confirmClearNotebook()" class="px-3.5 py-2.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-bold cursor-pointer">🗑️ Limpar</button>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-4 gap-3 mt-5 pt-5 border-t border-slate-100">
          <div class="bg-slate-50 rounded-xl p-3.5 border border-slate-200">
            <div class="text-xs font-semibold text-slate-500">Total no Caderno</div>
            <div id="nb-total-count" class="text-2xl font-black text-slate-900 mt-0.5">0</div>
          </div>
          <div class="bg-rose-50 rounded-xl p-3.5 border border-rose-200">
            <div class="text-xs font-semibold text-rose-700">Pendentes</div>
            <div id="nb-pending-count" class="text-2xl font-black text-rose-700 mt-0.5">0</div>
          </div>
          <div class="bg-emerald-50 rounded-xl p-3.5 border border-emerald-200">
            <div class="text-xs font-semibold text-emerald-700">Dominados</div>
            <div id="nb-mastered-count" class="text-2xl font-black text-emerald-700 mt-0.5">0</div>
          </div>
          <div class="bg-amber-50 rounded-xl p-3.5 border border-amber-200">
            <div class="text-xs font-semibold text-amber-800">Maior Ponto Fraco</div>
            <div id="nb-weakest-disc" class="text-sm font-extrabold text-amber-900 mt-1.5 truncate">—</div>
          </div>
        </div>
        <div id="notebook-weakness-bars" class="mt-4 space-y-2 hidden"></div>
      </div>

      <div id="notebook-list" class="space-y-5"></div>
    </section>
  </main>

  <script>
    const TEXTO_BASE_PORTUGUES = {json_texto_base};
    const QUESTIONS_DB = {json_questoes};
    const DISCIPLINE_META = {json_disciplinas};
    const INITIAL_TIMER_SECONDS = {tempo_segundos};
    const MIN_PASSING_PCT = {nota_minima_pct};

    const STORAGE_KEY_NOTEBOOK = "simulado_ia_caderno_erros_{storage_suffix}";
    const STORAGE_KEY_SESSION  = "simulado_ia_sessao_{storage_suffix}";

    let state = {{
      activeTab: "prova",
      examMode: "ALL",
      disciplineFilter: "ALL",
      userAnswers: {{}},
      eliminatedOpts: {{}},
      flaggedQuestions: {{}},
      baseTextCollapsed: false,
      isSubmitted: false,
      lastResult: null,
      resultFilter: "ALL",
      timerSeconds: INITIAL_TIMER_SECONDS,
      timerRunning: true,
      timerInterval: null,
      errorNotebook: []
    }};

    window.addEventListener("DOMContentLoaded", () => {{
      loadNotebookFromStorage();
      loadSessionFromStorage();
      renderExamView();
      renderAnswerGrid();
      updateSidebarCounters();
      updateNotebookBadge();
      renderErrorNotebook();
      if (state.isSubmitted && state.lastResult) renderResultView();
      startTimer();
    }});

    function loadNotebookFromStorage() {{
      try {{
        const raw = localStorage.getItem(STORAGE_KEY_NOTEBOOK);
        if (raw) state.errorNotebook = JSON.parse(raw) || [];
      }} catch (e) {{ state.errorNotebook = []; }}
    }}

    function saveNotebookToStorage() {{
      try {{
        localStorage.setItem(STORAGE_KEY_NOTEBOOK, JSON.stringify(state.errorNotebook));
        updateNotebookBadge();
      }} catch (e) {{}}
    }}

    function loadSessionFromStorage() {{
      try {{
        const raw = localStorage.getItem(STORAGE_KEY_SESSION);
        if (raw) {{
          const saved = JSON.parse(raw);
          state.examMode = saved.examMode || "ALL";
          state.userAnswers = saved.userAnswers || {{}};
          state.eliminatedOpts = saved.eliminatedOpts || {{}};
          state.flaggedQuestions = saved.flaggedQuestions || {{}};
          state.isSubmitted = Boolean(saved.isSubmitted);
          state.lastResult = saved.lastResult || null;
          if (typeof saved.timerSeconds === "number" && saved.timerSeconds > 0) state.timerSeconds = saved.timerSeconds;
        }}
      }} catch (e) {{}}
    }}

    function saveSessionToStorage() {{
      try {{
        localStorage.setItem(STORAGE_KEY_SESSION, JSON.stringify({{
          examMode: state.examMode, userAnswers: state.userAnswers,
          eliminatedOpts: state.eliminatedOpts, flaggedQuestions: state.flaggedQuestions,
          isSubmitted: state.isSubmitted, lastResult: state.lastResult, timerSeconds: state.timerSeconds
        }}));
      }} catch (e) {{}}
    }}

    function startTimer() {{
      if (state.timerInterval) clearInterval(state.timerInterval);
      updateTimerDisplay();
      state.timerInterval = setInterval(() => {{
        if (!state.timerRunning || state.isSubmitted) return;
        if (state.timerSeconds > 0) {{
          state.timerSeconds--;
          updateTimerDisplay();
          if (state.timerSeconds % 10 === 0) saveSessionToStorage();
        }} else {{
          clearInterval(state.timerInterval);
          executeFinishExam();
        }}
      }}, 1000);
    }}

    function toggleTimer() {{
      if (state.isSubmitted) return;
      state.timerRunning = !state.timerRunning;
      document.getElementById("timer-toggle-btn").textContent = state.timerRunning ? "Pausar" : "Retomar";
    }}

    function updateTimerDisplay() {{
      const hrs = Math.floor(state.timerSeconds / 3600);
      const mins = Math.floor((state.timerSeconds % 3600) / 60);
      const secs = state.timerSeconds % 60;
      document.getElementById("timer-display").textContent = [hrs, mins, secs].map(v => String(v).padStart(2, "0")).join(":");
    }}

    function formatSeconds(totalSec) {{
      const hrs = Math.floor(totalSec / 3600);
      const mins = Math.floor((totalSec % 3600) / 60);
      const secs = totalSec % 60;
      return hrs > 0 ? `${{String(hrs).padStart(2, "0")}}h ${{String(mins).padStart(2, "0")}}m` : `${{String(mins).padStart(2, "0")}}m ${{String(secs).padStart(2, "0")}}s`;
    }}

    function switchTab(tabName) {{
      state.activeTab = tabName;
      ["prova", "resultado", "caderno"].forEach(t => {{
        document.getElementById(`view-${{t}}`).classList.toggle("hidden", t !== tabName);
        const btn = document.getElementById(`tab-btn-${{t}}`);
        btn.className = t === tabName
          ? "tab-btn flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition whitespace-nowrap cursor-pointer bg-white text-navy-900 shadow-xs"
          : "tab-btn flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition whitespace-nowrap cursor-pointer text-navy-200 hover:bg-navy-800 hover:text-white";
      }});
      if (tabName === "resultado") renderResultView();
      if (tabName === "caderno") renderErrorNotebook();
    }}

    function getActiveExamQuestions() {{
      return state.examMode === "ALL" ? QUESTIONS_DB : QUESTIONS_DB.filter(q => q.disciplina === state.examMode);
    }}

    function handleModeChange() {{
      const select = document.getElementById("exam-mode-select");
      state.examMode = select.value;
      state.disciplineFilter = "ALL";
      state.userAnswers = {{}};
      state.eliminatedOpts = {{}};
      state.flaggedQuestions = {{}};
      state.isSubmitted = false;
      state.lastResult = null;
      state.timerSeconds = state.examMode === "ALL" ? INITIAL_TIMER_SECONDS : getActiveExamQuestions().length * 216;
      state.timerRunning = true;
      saveSessionToStorage();
      updateTimerDisplay();
      renderExamView();
      renderAnswerGrid();
      updateSidebarCounters();
      switchTab("prova");
    }}

    function confirmResetExam() {{
      openCustomModal({{
        title: "Reiniciar Tentativa Atual?",
        message: "Todas as alternativas marcadas serão zeradas. O Caderno de Erros permanecerá salvo.",
        confirmText: "Reiniciar",
        onConfirm: () => {{
          state.userAnswers = {{}};
          state.eliminatedOpts = {{}};
          state.flaggedQuestions = {{}};
          state.isSubmitted = false;
          state.lastResult = null;
          state.timerSeconds = INITIAL_TIMER_SECONDS;
          state.timerRunning = true;
          saveSessionToStorage();
          updateTimerDisplay();
          renderExamView();
          renderAnswerGrid();
          updateSidebarCounters();
          switchTab("prova");
        }}
      }});
    }}

    function setDisciplineViewFilter(disc) {{
      state.disciplineFilter = disc;
      document.querySelectorAll(".disc-pill").forEach(btn => {{
        const isSelected = btn.getAttribute("data-disc") === disc;
        btn.className = isSelected
          ? "disc-pill px-3 py-1.5 rounded-xl text-xs font-bold bg-navy-800 text-white transition cursor-pointer"
          : "disc-pill px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition cursor-pointer";
      }});
      renderExamView();
    }}

    function toggleBaseText() {{
      state.baseTextCollapsed = !state.baseTextCollapsed;
      const body = document.getElementById("base-text-body");
      if (body) body.classList.toggle("hidden", state.baseTextCollapsed);
    }}

    function renderExamView() {{
      const container = document.getElementById("questions-container");
      const activeQuestions = getActiveExamQuestions();
      const visibleQuestions = state.disciplineFilter === "ALL" ? activeQuestions : activeQuestions.filter(q => q.disciplina === state.disciplineFilter);
      const hasAnyBaseText = visibleQuestions.some(q => q.hasBaseText);

      let html = "";
      if (hasAnyBaseText && TEXTO_BASE_PORTUGUES && TEXTO_BASE_PORTUGUES.paragrafos) {{
        html += `
          <div class="bg-navy-50/90 border border-navy-200 rounded-2xl p-5 sm:p-6 shadow-xs">
            <div class="flex items-center justify-between pb-3 border-b border-navy-200/80">
              <div>
                <span class="px-2.5 py-0.5 rounded-md text-[11px] font-extrabold uppercase bg-navy-800 text-white">Texto-Base</span>
                <h3 class="text-base font-extrabold text-navy-900 mt-1">${{TEXTO_BASE_PORTUGUES.titulo}}</h3>
              </div>
              <button onclick="toggleBaseText()" class="px-3 py-1.5 rounded-xl bg-white text-navy-800 border border-navy-200 text-xs font-bold cursor-pointer">Alternar Texto</button>
            </div>
            <div id="base-text-body" class="${{state.baseTextCollapsed ? "hidden" : "block"}} mt-4 space-y-3 text-sm text-slate-800 leading-relaxed text-justify">
              ${{TEXTO_BASE_PORTUGUES.paragrafos.map((p, i) => `<p class="indent-6"><span class="text-[11px] font-mono text-navy-400 mr-1">[${{i + 1}}º §]</span>${{p}}</p>`).join("")}}
              <p class="text-xs italic text-slate-500 pt-2 border-t border-navy-200/60">Fonte: ${{TEXTO_BASE_PORTUGUES.autor}}</p>
            </div>
          </div>`;
      }}

      visibleQuestions.forEach(q => {{
        const selectedOpt = state.userAnswers[q.id] || null;
        const isFlagged = Boolean(state.flaggedQuestions[q.id]);
        const elimMap = state.eliminatedOpts[q.id] || {{}};

        html += `
          <article id="question-card-${{q.id}}" class="bg-white rounded-2xl shadow-xs border ${{isFlagged ? "border-amber-400 ring-2 ring-amber-100" : "border-slate-200"}} p-5 sm:p-6">
            <div class="flex flex-wrap items-center justify-between gap-2 pb-3.5 border-b border-slate-100">
              <div class="flex items-center gap-2">
                <span class="w-9 h-9 rounded-xl bg-navy-900 text-white font-extrabold text-sm flex items-center justify-center">${{String(q.id).padStart(2, "0")}}</span>
                <div>
                  <span class="px-2.5 py-0.5 rounded-lg text-[11px] font-bold bg-navy-50 text-navy-800 border border-navy-100">${{q.disciplina}}</span>
                  <p class="text-xs font-semibold text-slate-500 mt-1">${{q.topico}}</p>
                </div>
              </div>
              <button onclick="toggleFlagQuestion(${{q.id}})" class="px-3 py-1.5 rounded-xl text-xs font-bold border cursor-pointer ${{isFlagged ? "bg-amber-100 text-amber-900 border-amber-300" : "bg-slate-50 text-slate-600 border-slate-200"}}">
                🚩 ${{isFlagged ? "Marcada" : "Dúvida"}}
              </button>
            </div>
            <div class="mt-4 text-sm sm:text-[15px] text-slate-800 font-medium leading-relaxed whitespace-pre-line">${{q.enunciado}}</div>
            <div class="mt-4 space-y-2.5">
              ${{["A", "B", "C", "D", "E"].map(letter => {{
                const isSelected = selectedOpt === letter;
                const isEliminated = Boolean(elimMap[letter]);
                return `
                  <div class="flex items-stretch gap-2">
                    <button type="button" onclick="selectOption(${{q.id}}, '${{letter}}')" class="flex-1 text-left p-3 rounded-xl border transition flex items-start gap-3 cursor-pointer ${{isSelected ? "bg-navy-900 text-white border-navy-900" : isEliminated ? "bg-slate-50 text-slate-400 border-slate-200 line-through opacity-60" : "bg-white hover:bg-navy-50/60 text-slate-800 border-slate-200"}}">
                      <span class="w-7 h-7 rounded-lg font-extrabold text-xs flex items-center justify-center shrink-0 mt-0.5 ${{isSelected ? "bg-emerald-500 text-white" : "bg-slate-100 text-navy-900"}}">${{letter}}</span>
                      <span class="text-xs sm:text-sm leading-relaxed flex-1">${{q.alternativas[letter]}}</span>
                    </button>
                    <button type="button" onclick="toggleEliminateOption(${{q.id}}, '${{letter}}')" class="px-2.5 rounded-xl border text-xs font-bold cursor-pointer ${{isEliminated ? "bg-rose-100 text-rose-700 border-rose-300" : "bg-slate-50 text-slate-400 border-slate-200"}}">✂️</button>
                  </div>`;
              }}).join("")}}
            </div>
          </article>`;
      }});
      container.innerHTML = html;
    }}

    function selectOption(qId, letter) {{
      if (state.userAnswers[qId] === letter) delete state.userAnswers[qId];
      else state.userAnswers[qId] = letter;
      saveSessionToStorage();
      renderExamView();
      renderAnswerGrid();
      updateSidebarCounters();
    }}

    function toggleEliminateOption(qId, letter) {{
      if (!state.eliminatedOpts[qId]) state.eliminatedOpts[qId] = {{}};
      state.eliminatedOpts[qId][letter] = !state.eliminatedOpts[qId][letter];
      if (state.eliminatedOpts[qId][letter] && state.userAnswers[qId] === letter) delete state.userAnswers[qId];
      saveSessionToStorage();
      renderExamView();
      renderAnswerGrid();
      updateSidebarCounters();
    }}

    function toggleFlagQuestion(qId) {{
      if (state.flaggedQuestions[qId]) delete state.flaggedQuestions[qId];
      else state.flaggedQuestions[qId] = true;
      saveSessionToStorage();
      renderExamView();
      renderAnswerGrid();
      updateSidebarCounters();
    }}

    function renderAnswerGrid() {{
      const grid = document.getElementById("answer-grid");
      grid.innerHTML = getActiveExamQuestions().map(q => {{
        const ans = state.userAnswers[q.id];
        const flagged = Boolean(state.flaggedQuestions[q.id]);
        let classes = ans ? "bg-navy-800 text-white border-navy-900" : flagged ? "bg-amber-100 text-amber-900 border-amber-400" : "bg-slate-100 text-slate-600 border-slate-200";
        return `<button type="button" onclick="scrollToQuestion(${{q.id}})" class="py-2 px-1 rounded-lg border text-[11px] font-extrabold flex flex-col items-center cursor-pointer ${{classes}}"><span>${{String(q.id).padStart(2, "0")}}</span><span class="text-[10px]">${{ans || "—"}}</span></button>`;
      }}).join("");
    }}

    function updateSidebarCounters() {{
      const activeQuestions = getActiveExamQuestions();
      const total = activeQuestions.length;
      const answered = activeQuestions.filter(q => Boolean(state.userAnswers[q.id])).length;
      const flagged = activeQuestions.filter(q => Boolean(state.flaggedQuestions[q.id])).length;
      document.getElementById("stat-answered").textContent = answered;
      document.getElementById("stat-unanswered").textContent = total - answered;
      document.getElementById("stat-flagged").textContent = flagged;
      document.getElementById("sidebar-completion-pct").textContent = `${{total > 0 ? Math.round((answered / total) * 100) : 0}}%`;
      document.getElementById("nav-progress-badge").textContent = `${{answered}}/${{total}}`;
    }}

    function scrollToQuestion(qId) {{
      if (state.disciplineFilter !== "ALL") setDisciplineViewFilter("ALL");
      setTimeout(() => {{
        const el = document.getElementById(`question-card-${{qId}}`);
        if (el) window.scrollTo({{ top: el.getBoundingClientRect().top + window.pageYOffset - 100, behavior: "smooth" }});
      }}, 40);
    }}

    function scrollToFirstUnanswered() {{
      const firstBlank = getActiveExamQuestions().find(q => !state.userAnswers[q.id]);
      if (firstBlank) scrollToQuestion(firstBlank.id);
      else showToast("Todas as questões já foram respondidas!", "success");
    }}

    function openFinishModal() {{
      openCustomModal({{
        title: "Finalizar e Corrigir Simulado?",
        message: "Sua nota será calculada e os erros irão automaticamente para o Caderno de Erros.",
        confirmText: "Finalizar Agora",
        onConfirm: executeFinishExam
      }});
    }}

    function executeFinishExam() {{
      state.isSubmitted = true;
      state.timerRunning = false;
      const activeQuestions = getActiveExamQuestions();
      const timeSpent = Math.max(0, INITIAL_TIMER_SECONDS - state.timerSeconds);

      let totalHits = 0, totalErrors = 0, totalBlank = 0;
      const byDiscipline = {{}};
      DISCIPLINE_META.forEach(d => {{
        byDiscipline[d.name] = {{ ...d, activeCount: 0, hits: 0, errors: 0, blank: 0, points: 0 }};
      }});

      activeQuestions.forEach(q => {{
        const userAns = state.userAnswers[q.id] || null;
        const discObj = byDiscipline[q.disciplina];
        if (discObj) discObj.activeCount++;
        if (!userAns) {{
          totalBlank++;
          if (discObj) discObj.blank++;
        }} else if (userAns === q.correta) {{
          totalHits++;
          if (discObj) {{ discObj.hits++; discObj.points = Number((discObj.points + 0.2).toFixed(2)); }}
        }} else {{
          totalErrors++;
          if (discObj) discObj.errors++;
          addOrUpdateErrorInNotebook(q.id, userAns);
        }}
      }});

      const finalScore = Number((totalHits * 0.2).toFixed(2));
      const maxScore = Number((activeQuestions.length * 0.2).toFixed(2));
      const minPassingScore = Number((maxScore * MIN_PASSING_PCT).toFixed(2));

      state.lastResult = {{
        mode: state.examMode, totalHits, totalErrors, totalBlank, finalScore, maxScore,
        minPassingScore, passed: finalScore >= minPassingScore, timeSpent, byDiscipline,
        snapshotAnswers: {{ ...state.userAnswers }}
      }};

      saveNotebookToStorage();
      saveSessionToStorage();
      const scoreBadge = document.getElementById("nav-score-badge");
      scoreBadge.textContent = `${{finalScore.toFixed(1).replace(".", ",")}} pts`;
      scoreBadge.classList.remove("hidden");
      renderResultView();
      renderErrorNotebook();
      switchTab("resultado");
    }}

    function addOrUpdateErrorInNotebook(qId, wrongOption) {{
      const idx = state.errorNotebook.findIndex(i => i.questionId === qId);
      const now = new Date().toLocaleDateString("pt-BR");
      if (idx >= 0) {{
        state.errorNotebook[idx].errorCount += 1;
        state.errorNotebook[idx].lastWrongOption = wrongOption;
        state.errorNotebook[idx].lastUpdated = now;
        state.errorNotebook[idx].status = "PENDING";
      }} else {{
        state.errorNotebook.unshift({{ questionId: qId, errorCount: 1, lastWrongOption: wrongOption, status: "PENDING", userNote: "", lastUpdated: now }});
      }}
    }}

    function manualAddToNotebook(qId) {{
      if (state.errorNotebook.some(i => i.questionId === qId)) return;
      state.errorNotebook.unshift({{ questionId: qId, errorCount: 1, lastWrongOption: "Acerto no chute", status: "PENDING", userNote: "", lastUpdated: new Date().toLocaleDateString("pt-BR") }});
      saveNotebookToStorage();
      renderCommentedKey();
      renderErrorNotebook();
      showToast("Questão adicionada ao Caderno de Erros!", "success");
    }}

    function renderResultView() {{
      if (!state.isSubmitted || !state.lastResult) return;
      document.getElementById("resultado-empty-state").classList.add("hidden");
      document.getElementById("resultado-content").classList.remove("hidden");

      const r = state.lastResult;
      document.getElementById("res-final-score").textContent = r.finalScore.toFixed(1).replace(".", ",");
      document.getElementById("res-max-score").textContent = r.maxScore.toFixed(1).replace(".", ",");
      document.getElementById("res-total-hits").textContent = r.totalHits;
      document.getElementById("res-total-errors").textContent = r.totalErrors;
      document.getElementById("res-total-blank").textContent = r.totalBlank;
      document.getElementById("res-time-spent").textContent = formatSeconds(r.timeSpent);

      const statusBadge = document.getElementById("res-status-badge");
      statusBadge.className = r.passed
        ? "mt-3 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-400/40"
        : "mt-3 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-extrabold bg-rose-500/20 text-rose-200 border border-rose-400/40";
      statusBadge.innerHTML = r.passed ? `✅ APROVADO (≥ ${{r.minPassingScore.toFixed(1).replace(".", ",")}} pts)` : `❌ ABAIXO DA NOTA DE CORTE (${{r.minPassingScore.toFixed(1).replace(".", ",")}} pts)`;

      document.getElementById("res-discipline-table-body").innerHTML = DISCIPLINE_META.map(meta => {{
        const d = r.byDiscipline[meta.name];
        if (!d || d.activeCount === 0) return "";
        const pct = Math.round((d.hits / d.activeCount) * 100);
        return `
          <tr class="hover:bg-slate-50">
            <td class="py-3 px-3"><span class="px-2 py-0.5 rounded-md text-[11px] font-bold bg-navy-100 text-navy-800">${{d.tieOrder}}</span></td>
            <td class="py-3 px-3 font-bold text-slate-900">${{d.name}}</td>
            <td class="py-3 px-3 text-center">${{d.activeCount}}</td>
            <td class="py-3 px-3 text-center text-emerald-700 font-extrabold">${{d.hits}}</td>
            <td class="py-3 px-3 text-center text-rose-600 font-bold">${{d.errors}}</td>
            <td class="py-3 px-3 text-center font-bold">${{pct}}%</td>
            <td class="py-3 px-3 text-right font-extrabold text-navy-900">${{d.points.toFixed(1).replace(".", ",")}} pts</td>
          </tr>`;
      }}).join("");

      renderCommentedKey();
    }}

    function setResultFilter(f) {{ state.resultFilter = f; renderCommentedKey(); }}

    function renderCommentedKey() {{
      if (!state.lastResult) return;
      const listEl = document.getElementById("commented-key-list");
      const discFilter = document.getElementById("res-discipline-filter").value;
      const r = state.lastResult;
      const baseQuestions = r.mode === "ALL" ? QUESTIONS_DB : QUESTIONS_DB.filter(q => q.disciplina === r.mode);

      const filtered = baseQuestions.filter(q => {{
        const userAns = r.snapshotAnswers[q.id] || null;
        if (state.resultFilter === "WRONG" && (userAns === null || userAns === q.correta)) return false;
        if (state.resultFilter === "CORRECT" && userAns !== q.correta) return false;
        if (discFilter !== "ALL" && q.disciplina !== discFilter) return false;
        return true;
      }});

      listEl.innerHTML = filtered.map(q => {{
        const userAns = r.snapshotAnswers[q.id] || null;
        const isCorrect = userAns === q.correta;
        const inNotebook = state.errorNotebook.some(i => i.questionId === q.id);

        return `
          <div class="rounded-2xl border ${{isCorrect ? "border-emerald-200" : "border-rose-300"}} bg-white p-5">
            <div class="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-100">
              <span class="text-xs font-extrabold text-navy-900">Questão ${{String(q.id).padStart(2, "0")}} • ${{q.disciplina}} (${{q.topico}})</span>
              <div class="flex items-center gap-2">
                <span class="px-2.5 py-1 rounded-full text-xs font-extrabold ${{isCorrect ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}}">
                  ${{isCorrect ? "✅ ACERTOU" : `❌ ERROU (Marcou ${{userAns || "Branco"}} • Gabarito ${{q.correta}})`}}
                </span>
                ${{!inNotebook ? `<button onclick="manualAddToNotebook(${{q.id}})" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-100 text-navy-800 cursor-pointer">+ Caderno</button>` : ""}}
              </div>
            </div>
            <p class="mt-3 text-sm font-medium text-slate-800 whitespace-pre-line">${{q.enunciado}}</p>
            <div class="mt-3 space-y-2">
              ${{["A", "B", "C", "D", "E"].map(l => `
                <div class="p-2.5 rounded-xl border text-xs ${{l === q.correta ? "bg-emerald-50 border-emerald-400 font-bold" : l === userAns ? "bg-rose-50 border-rose-400" : "bg-slate-50 border-slate-200"}}">
                  <strong>(${{l}})</strong> ${{q.alternativas[l]}}
                </div>`).join("")}}
            </div>
            <div class="mt-4 bg-navy-50/80 border border-navy-200 rounded-xl p-4 space-y-2 text-xs">
              <p class="text-slate-800"><strong>📘 Justificativa (${{q.correta}}):</strong> ${{q.justificativaCorreta}}</p>
              <ul class="space-y-1 text-slate-700 pt-2 border-t border-navy-200">
                ${{["A", "B", "C", "D", "E"].map(l => `<li><strong>(${{l}})</strong> ${{q.analiseErros[l]}}</li>`).join("")}}
              </ul>
            </div>
          </div>`;
      }}).join("");
    }}

    function updateNotebookBadge() {{
      document.getElementById("nav-errors-badge").textContent = state.errorNotebook.filter(i => i.status === "PENDING").length;
    }}

    function renderErrorNotebook() {{
      const total = state.errorNotebook.length;
      const pending = state.errorNotebook.filter(i => i.status === "PENDING").length;
      document.getElementById("nb-total-count").textContent = total;
      document.getElementById("nb-pending-count").textContent = pending;
      document.getElementById("nb-mastered-count").textContent = total - pending;

      const listEl = document.getElementById("notebook-list");
      if (total === 0) {{
        listEl.innerHTML = `<div class="bg-white rounded-2xl border border-slate-200 p-8 text-center text-sm text-slate-500">Seu Caderno de Erros está vazio. Finalize um simulado para registrar suas falhas automaticamente.</div>`;
        return;
      }}

      listEl.innerHTML = state.errorNotebook.map(entry => {{
        const q = QUESTIONS_DB.find(item => item.id === entry.questionId);
        if (!q) return "";
        const isMastered = entry.status === "MASTERED";
        return `
          <article class="bg-white rounded-2xl border ${{isMastered ? "border-emerald-300" : "border-rose-200"}} p-5">
            <div class="flex justify-between items-center pb-3 border-b border-slate-100">
              <span class="text-xs font-extrabold text-navy-900">Questão ${{String(q.id).padStart(2, "0")}} • ${{q.disciplina}} (Errou ${{entry.errorCount}}x)</span>
              <button onclick="toggleNotebookItemStatus(${{q.id}})" class="px-3 py-1 rounded-xl text-xs font-bold bg-slate-100 cursor-pointer">${{isMastered ? "✅ Dominado" : "Marcar Dominado"}}</button>
            </div>
            <p class="mt-3 text-sm text-slate-800">${{q.enunciado}}</p>
            <div class="mt-3 bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs">
              <strong>Gabarito (${{q.correta}}):</strong> ${{q.alternativas[q.correta]}}<br/>
              <span class="mt-1 block">${{q.justificativaCorreta}}</span>
            </div>
            <textarea rows="2" oninput="updateNotebookUserNote(${{q.id}}, this.value)" placeholder="Sua Regra de Ouro..." class="mt-3 w-full rounded-xl border border-slate-300 p-2 text-xs">${{entry.userNote || ""}}</textarea>
          </article>`;
      }}).join("");
    }}

    function toggleNotebookItemStatus(qId) {{
      const item = state.errorNotebook.find(i => i.questionId === qId);
      if (item) {{ item.status = item.status === "MASTERED" ? "PENDING" : "MASTERED"; saveNotebookToStorage(); renderErrorNotebook(); }}
    }}

    function updateNotebookUserNote(qId, val) {{
      const item = state.errorNotebook.find(i => i.questionId === qId);
      if (item) {{ item.userNote = val; saveNotebookToStorage(); }}
    }}

    function confirmClearNotebook() {{
      state.errorNotebook = [];
      saveNotebookToStorage();
      renderErrorNotebook();
    }}

    function generateNotebookMarkdownText() {{
      return state.errorNotebook.map((entry, idx) => {{
        const q = QUESTIONS_DB.find(i => i.id === entry.questionId);
        return q ? `### ${{idx + 1}}. Q${{q.id}} (${{q.disciplina}})\n- **Enunciado:** ${{q.enunciado}}\n- **Gabarito:** ${{q.correta}}\n- **Regra de Ouro:** ${{entry.userNote}}\n` : "";
      }}).join("\n");
    }}

    function copyNotebookMarkdown() {{
      const ta = document.createElement("textarea");
      ta.value = generateNotebookMarkdownText();
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      showToast("Copiado em Markdown!", "success");
    }}

    function downloadNotebookMarkdown() {{
      const blob = new Blob([generateNotebookMarkdownText()], {{ type: "text/markdown;charset=utf-8;" }});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "caderno_de_erros.md";
      a.click();
    }}

    function openCustomModal({{ title, message, confirmText, onConfirm }}) {{
      const modal = document.getElementById("custom-modal");
      document.getElementById("modal-title").textContent = title;
      document.getElementById("modal-message").textContent = message;
      document.getElementById("modal-confirm-btn").textContent = confirmText;
      document.getElementById("modal-confirm-btn").onclick = () => {{ modal.classList.add("hidden"); modal.classList.remove("flex"); if (onConfirm) onConfirm(); }};
      document.getElementById("modal-cancel-btn").onclick = () => {{ modal.classList.add("hidden"); modal.classList.remove("flex"); }};
      modal.classList.remove("hidden");
      modal.classList.add("flex");
    }}

    function showToast(msg, type = "info") {{
      const container = document.getElementById("toast-container");
      const toast = document.createElement("div");
      toast.className = "pointer-events-auto px-4 py-3 rounded-xl shadow-lg bg-navy-900 text-white text-xs font-semibold";
      toast.textContent = msg;
      container.appendChild(toast);
      setTimeout(() => toast.remove(), 3000);
    }}
  </script>
</body>
</html>"""
    return html_code


# ==============================================================================
# INTERFACE DE CONTROLE NO STREAMLIT (SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.title("⚙️ Gerador de Simulado IA")
    st.caption("A IA pesquisa o edital, identifica o padrão da banca e monta a prova na sua interface.")

    api_key = st.text_input(
        "Chave de API do Gemini",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
        help="Obtenha gratuitamente no Google AI Studio."
    )

    st.divider()

    concurso_orgao = st.text_input(
        "Concurso / Órgão",
        value="ALEPA 2026 (Assembleia Legislativa do Estado do Pará)"
    )

    banca = st.text_input(
        "Banca Examinadora",
        value="Fundação CETAP",
        help="Ex.: Fundação CETAP, FADESP, FGV, Cebraspe, Vunesp..."
    )

    cargo_edital = st.text_input(
        "Cargo / Edital",
        value="Cargo 04: Auxiliar Técnico Legislativo – Assistência Administrativa (Edital 001/2026)"
    )

    assuntos_pedido = st.text_area(
        "Assuntos ou Conteúdo Programático",
        height=130,
        value=(
            "1. Língua Portuguesa: Interpretação de texto, crase, concordância e redação oficial (MRPR).\n"
            "2. Legislação e Ética: Regimento Interno da ALEPA (Res. 02/2022), LGPD e Lei de Improbidade.\n"
            "3. Informática: Excel 365, Windows 11 e Segurança da Informação (Hardening).\n"
            "4. Conhecimentos Específicos: RJU/PA (Lei 5.810/94), Lei 14.133/21, Arquivologia e Curva ABC."
        ),
        help="Descreva os temas que deseja estudar ou cole tópicos do edital."
    )

    col1, col2 = st.columns(2)
    with col1:
        qtd_questoes = st.number_input("Nº de Questões", min_value=5, max_value=50, value=15, step=5)
    with col2:
        nivel_dificuldade = st.selectbox("Nível", ["Padrão da Banca", "Intermediário", "Difícil / Pegadinhas"])

    gerar_btn = st.button("🔍 Pesquisar Banca e Gerar Simulado", type="primary", use_container_width=True)

# ==============================================================================
# EXECUÇÃO E RENDERIZAÇÃO DA PLATAFORMA
# ==============================================================================
if gerar_btn:
    if not api_key:
        st.error("⚠️ Informe sua chave de API do Gemini na barra lateral para continuar.")
    elif not assuntos_pedido.strip():
        st.warning("⚠️ Informe pelo menos um assunto ou disciplina.")
    else:
        with st.spinner(f"Pesquisando o padrão da banca {banca} e elaborando {qtd_questoes} questões inéditas..."):
            try:
                dados = gerar_simulado_com_ia(
                    api_key=api_key,
                    concurso_orgao=concurso_orgao,
                    banca=banca,
                    cargo_edital=cargo_edital,
                    assuntos_pedido=assuntos_pedido,
                    qtd_questoes=qtd_questoes,
                    nivel_dificuldade=nivel_dificuldade
                )
                st.session_state["simulado_atual"] = dados
                st.success("✅ Simulado gerado com sucesso! Role ou utilize a plataforma abaixo.")
            except Exception as e:
                st.error(f"Erro ao gerar o simulado: {e}")

if "simulado_atual" in st.session_state:
    html_renderizado = renderizar_plataforma_html(st.session_state["simulado_atual"])
    # Renderiza sua plataforma completa dentro do Streamlit
    components.html(html_renderizado, height=1100, scrolling=True)
else:
    st.info("👈 Preencha os dados do concurso, a banca e os assuntos na barra lateral e clique em **Pesquisar Banca e Gerar Simulado**.")
